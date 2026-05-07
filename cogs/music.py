import discord
from discord.ext import commands
import yt_dlp
import asyncio
from collections import deque
import os
from dotenv import load_dotenv

load_dotenv()

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extract_flat': True,
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'default_search': 'ytsearch'
}

STREAM_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -loglevel quiet'
}

class MusicControlView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=None)
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="循環: 關", style=discord.ButtonStyle.gray)
    async def toggle_loop(self, interaction, button):
        guild_id = interaction.guild.id
        current_state = self.cog.loops.get(guild_id, False)
        new_state = not current_state
        self.cog.loops[guild_id] = new_state
        button.label = f"循環: {'開' if new_state else '關'}"
        button.style = discord.ButtonStyle.green if new_state else discord.ButtonStyle.gray
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="暫停/繼續", style=discord.ButtonStyle.blurple)
    async def toggle(self, interaction, button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing(): vc.pause()
            elif vc.is_paused(): vc.resume()
            await interaction.response.send_message("切換狀態", ephemeral=True)

    @discord.ui.button(label="跳過", style=discord.ButtonStyle.green)
    async def skip(self, interaction, button):
        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("已跳過", ephemeral=True)

    @discord.ui.button(label="停止", style=discord.ButtonStyle.red)
    async def stop(self, interaction, button):
        await self.cog.clear_queue(interaction.guild)
        await interaction.response.send_message("已停止", ephemeral=True)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.loops = {}
        self.current_track = {}
        self.panel_messages = {}
        self.empty_channel_tasks = {}

    def get_queue(self, guild_id):
        if guild_id not in self.queues: self.queues[guild_id] = deque()
        return self.queues[guild_id]

    async def clear_queue(self, guild):
        guild_id = guild.id
        if guild_id in self.queues: self.queues[guild_id].clear()
        self.loops[guild_id] = False
        self.current_track.pop(guild_id, None)
        self.panel_messages.pop(guild_id, None)
        if guild.voice_client: 
            await guild.voice_client.disconnect()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id:
            if after.channel is None:
                guild_id = member.guild.id
                if guild_id in self.queues:
                    self.queues[guild_id].clear()
                    self.loops[guild_id] = False
                    self.panel_messages.pop(guild_id, None)

    async def play_next(self, ctx):
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        
        # 預設 track_info 為 None 避免未定義錯誤
        track_info = None

        if self.loops.get(guild_id) and guild_id in self.current_track:
            track_info = self.current_track[guild_id]
        elif queue:
            track_info = queue.popleft()
            self.current_track[guild_id] = track_info
        
        # 如果沒歌了，清理狀態並退出
        if not track_info:
            if guild_id in self.panel_messages:
                try: await self.panel_messages[guild_id].delete()
                except: pass
                self.panel_messages.pop(guild_id, None)
            return

        # 這裡才進行解包
        url, title, thumbnail = track_info

        async with ctx.typing():
            with yt_dlp.YoutubeDL(STREAM_OPTIONS) as ydl:
                try:
                    s_url = url if "http" in url else f"ytsearch:{url}"
                    info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(s_url, download=False))
                    if 'entries' in info: info = info['entries'][0]
                    stream_url = info['url']
                except:
                    # 遇到壞歌自動跳過
                    return await self.play_next(ctx)

            source = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(ctx)))
        
        embed = discord.Embed(
            title="🎶 正在播放", 
            description=f"**[{title}]({url})**", 
            color=discord.Color.from_rgb(255, 0, 0)
        )
        
        # 使用 set_image 確保大圖，thumbnail 網址必須是 maxresdefault 比例才穩
        if thumbnail:
            embed.set_image(url=thumbnail)
        
        if self.loops.get(guild_id):
            embed.set_footer(text="🔂 單曲循環開啟中")
            
        view = MusicControlView(self, ctx)

        # 💡 解決「閃一下變小」的終極方案：刪除舊訊息發送新訊息
        if guild_id in self.panel_messages:
            try: await self.panel_messages[guild_id].delete()
            except: pass
        
        self.panel_messages[guild_id] = await ctx.send(embed=embed, view=view)

        # 這裡解包三個參數：網址、標題、圖片
        url, title, thumbnail = track_info

        async with ctx.typing():
            with yt_dlp.YoutubeDL(STREAM_OPTIONS) as ydl:
                try:
                    search_url = url if "http" in url else f"ytsearch:{url}"
                    info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(search_url, download=False))
                    if 'entries' in info: info = info['entries'][0]
                    stream_url = info['url']
                except:
                    # 如果這首歌解析失敗，自動跳下一首
                    return await self.play_next(ctx)

            # 使用高效能的 FFmpeg 解析
            source = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(ctx)))
        
        # 建立 Embed 介面
        embed = discord.Embed(
            title="🎶 正在播放", 
            description=f"**[{title}]({url})**", 
            color=discord.Color.red()
        )
        
        # 關鍵修改：將 set_thumbnail 改為 set_image 讓圖片變大
        if thumbnail:
            embed.set_image(url=thumbnail)
        
        if self.loops.get(guild_id):
            embed.set_footer(text="🔂 單曲循環開啟中")
            
        view = MusicControlView(self, ctx)

        # 更新或發送播放面板
        if guild_id in self.panel_messages:
            try:
                await self.panel_messages[guild_id].edit(embed=embed, view=view)
            except:
                self.panel_messages[guild_id] = await ctx.send(embed=embed, view=view)
        else:
            self.panel_messages[guild_id] = await ctx.send(embed=embed, view=view)
        
        embed = discord.Embed(
            title="🎶 正在播放", 
            description=f"**[{title}]({url})**", 
            color=discord.Color.from_rgb(255, 0, 0)
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if self.loops.get(guild_id):
            embed.set_footer(text="🔂 單曲循環中")
            
        view = MusicControlView(self, ctx)

        if guild_id in self.panel_messages:
            try: await self.panel_messages[guild_id].edit(embed=embed, view=view)
            except: self.panel_messages[guild_id] = await ctx.send(embed=embed, view=view)
        else:
            self.panel_messages[guild_id] = await ctx.send(embed=embed, view=view)

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, search: str):
        if not ctx.author.voice: return await ctx.send("❌ 請先進入語音頻道")
        if not ctx.voice_client: await ctx.author.voice.channel.connect(self_deaf=True)

        queue = self.get_queue(ctx.guild.id)
        msg = await ctx.send("🔍 讀取中...")

        async with ctx.typing():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                try:
                    info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(search, download=False))
                    
                    if 'entries' in info and len(info['entries']) > 1:
                        count = 0
                        for entry in info['entries']:
                            if entry:
                                # 💡 關鍵修改：強制組出 16:9 的高品質影片縮圖，而非 1:1 的封面圖
                                v_id = entry.get('id')
                                # 使用 maxresdefault.jpg 可以獲得最高的解析度與正確的 16:9 比例
                                thumbnail = f"https://img.youtube.com/vi/{v_id}/maxresdefault.jpg"
                                
                                queue.append((entry['url'], entry['title'], thumbnail))
                                count += 1
                        await msg.edit(content=f"✅ 已匯入 **{count}** 首歌曲")
                    else:
                        entry = info['entries'][0] if 'entries' in info else info
                        v_url = entry.get('webpage_url') or entry.get('url')
                        queue.append((v_url, entry['title'], entry.get('thumbnail')))
                        await msg.edit(content=f"✅ 已加入: **{entry['title']}**")
                except Exception as e:
                    await msg.edit(content=f"❌ 錯誤: {e}")
                    return

        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            await self.play_next(ctx)

    @commands.command(name="stop")
    async def stop_cmd(self, ctx): 
        await self.clear_queue(ctx.guild)
        await ctx.send("👋 已停止")

async def setup(bot):
    await bot.add_cog(Music(bot))