import discord
from discord.ext import commands
import yt_dlp
import asyncio
from collections import deque

YDL_OPTIONS = {'format': 'bestaudio/best', 'extract_flat': 'in_playlist', 'quiet': True, 'no_warnings': True}
STREAM_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True}
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

class MusicControlView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=None)
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="循環: 關", style=discord.ButtonStyle.gray)
    async def toggle_loop(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        await self.cog.clear_queue(self.ctx)
        await interaction.response.send_message("已停止", ephemeral=True)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.loops = {}
        self.current_track = {}
        self.panel_messages = {} # 儲存每個伺服器的控制面板訊息物件

    def get_queue(self, guild_id):
        if guild_id not in self.queues: self.queues[guild_id] = deque()
        return self.queues[guild_id]

    async def clear_queue(self, ctx):
        guild_id = ctx.guild.id
        if guild_id in self.queues: self.queues[guild_id].clear()
        self.loops[guild_id] = False
        self.panel_messages.pop(guild_id, None)
        if ctx.voice_client: await ctx.voice_client.disconnect()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        vc = member.guild.voice_client
        if vc and len(vc.channel.members) == 1:
            await self.clear_queue(member)

    async def play_next(self, ctx):
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        
        if self.loops.get(guild_id) and guild_id in self.current_track:
            url, title = self.current_track[guild_id]
        elif queue:
            url, title = queue.popleft()
            self.current_track[guild_id] = (url, title)
        else:
            self.panel_messages.pop(guild_id, None)
            return

        async with ctx.typing():
            with yt_dlp.YoutubeDL(STREAM_OPTIONS) as ydl:
                try:
                    info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(url if "http" in url else f"ytsearch:{url}", download=False))
                    if 'entries' in info: info = info['entries'][0]
                    stream_url = info['url']
                except:
                    return await self.play_next(ctx)

            source = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(ctx)))
        
        # 編輯現有訊息或發送新訊息
        content = f"正在播放: **{title}** {' (單曲循環中)' if self.loops.get(guild_id) else ''}"
        view = MusicControlView(self, ctx)

        if guild_id in self.panel_messages:
            try:
                await self.panel_messages[guild_id].edit(content=content, view=view)
            except: # 如果訊息被刪除了，就重新發一個
                self.panel_messages[guild_id] = await ctx.send(content, view=view)
        else:
            self.panel_messages[guild_id] = await ctx.send(content, view=view)

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, search: str):
        if not ctx.author.voice: return await ctx.send("你必須先加入語音頻道")
        if not ctx.voice_client: await ctx.author.voice.channel.connect()

        async with ctx.typing():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = await self.bot.loop.run_in_executor(None, lambda: ydl.extract_info(search if "http" in search else f"ytsearch:{search}", download=False))
                queue = self.get_queue(ctx.guild.id)
                if 'entries' in info:
                    if search.startswith("http"):
                        for e in info['entries']: queue.append((e['url'], e['title']))
                        await ctx.send(f"已加入清單: {len(info['entries'])} 首歌", delete_after=5)
                    else:
                        e = info['entries'][0]
                        queue.append((e['url'], e['title']))
                        await ctx.send(f"已加入: **{e['title']}**", delete_after=5)
                else:
                    queue.append((info['webpage_url'], info['title']))
                    await ctx.send(f"已加入: **{info['title']}**", delete_after=5)

        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            await self.play_next(ctx)

    @commands.command(name="stop")
    async def stop_cmd(self, ctx): await self.clear_queue(ctx)

async def setup(bot):
    await bot.add_cog(Music(bot))