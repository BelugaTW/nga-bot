import discord
from discord.ext import commands
import yt_dlp
import asyncio
from collections import deque

# 基礎解析設定：確保 extract_flat 能抓到清單內所有 entry
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extract_flat': 'in_playlist',  # 強制抓取清單內所有項目
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,           # 跳過清單中失效或私人的影片
}

STREAM_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

class MusicControlView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=None)
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="音量-", style=discord.ButtonStyle.gray)
    async def volume_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.source:
            new_vol = max(0.0, vc.source.volume - 0.1)
            vc.source.volume = new_vol
            await interaction.response.send_message(f"音量: {int(new_vol * 100)}%", ephemeral=True)

    @discord.ui.button(label="暫停/繼續", style=discord.ButtonStyle.blurple)
    async def toggle_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc: return
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message("已暫停", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message("繼續播放", ephemeral=True)

    @discord.ui.button(label="音量+", style=discord.ButtonStyle.gray)
    async def volume_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.source:
            new_vol = min(2.0, vc.source.volume + 0.1)
            vc.source.volume = new_vol
            await interaction.response.send_message(f"音量: {int(new_vol * 100)}%", ephemeral=True)

    @discord.ui.button(label="跳過", style=discord.ButtonStyle.green)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("已跳過", ephemeral=True)

    @discord.ui.button(label="停止", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.clear_queue(self.ctx)
        await interaction.response.send_message("已停止", ephemeral=True)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.volume = 0.5

    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = deque()
        return self.queues[guild_id]

    async def clear_queue(self, ctx):
        if ctx.guild.id in self.queues: self.queues[ctx.guild.id].clear()
        if ctx.voice_client: await ctx.voice_client.disconnect()

    async def play_next(self, ctx):
        queue = self.get_queue(ctx.guild.id)
        if not queue: return

        url, title = queue.popleft()
        async with ctx.typing():
            with yt_dlp.YoutubeDL(STREAM_OPTIONS) as ydl:
                try:
                    info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
                    stream_url = info['url']
                except:
                    return await self.play_next(ctx)

            raw_source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(raw_source, volume=self.volume)
            ctx.voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(ctx)))
        
        await ctx.send(f"正在播放: **{title}**", view=MusicControlView(self, ctx))

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, search: str):
        if not ctx.author.voice: return await ctx.send("你必須先加入語音頻道")
        if not ctx.voice_client: await ctx.author.voice.channel.connect()

        async with ctx.typing():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                # 偵測是否為播放清單網址
                is_url = search.startswith("http")
                query = search if is_url else f"ytsearch:{search}"
                
                info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
                if not info: return await ctx.send("找不到結果")

                queue = self.get_queue(ctx.guild.id)
                
                # 核心邏輯：如果 entries 存在，代表抓到了清單或搜尋列表
                if 'entries' in info:
                    entries = [e for e in info['entries'] if e is not None]
                    
                    if is_url: # 處理播放清單網址
                        for e in entries:
                            video_url = e.get('url') or f"https://www.youtube.com/watch?v={e.get('id')}"
                            queue.append((video_url, e.get('title') or "未知歌曲"))
                        await ctx.send(f"已從清單偵測並加入 **{len(entries)}** 首歌至隊列")
                    else: # 處理一般關鍵字搜尋（只取第一筆）
                        e = entries[0]
                        video_url = e.get('url') or f"https://www.youtube.com/watch?v={e.get('id')}"
                        queue.append((video_url, e.get('title')))
                        await ctx.send(f"已加入隊列: **{e.get('title')}**")
                else:
                    # 處理單一影片網址
                    queue.append((info.get('webpage_url') or search, info.get('title')))
                    await ctx.send(f"已加入隊列: **{info.get('title')}**")

        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            await self.play_next(ctx)

    @commands.command(name="volume", aliases=["vol"])
    async def set_volume(self, ctx, vol: int):
        self.volume = max(0, min(vol, 200)) / 100
        if ctx.voice_client and ctx.voice_client.source:
            ctx.voice_client.source.volume = self.volume
        await ctx.send(f"音量已設定為: {vol}%")

    @commands.command(name="stop")
    async def stop_cmd(self, ctx):
        await self.clear_queue(ctx)

async def setup(bot):
    await bot.add_cog(Music(bot))
