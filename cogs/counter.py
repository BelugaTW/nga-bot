import discord
from discord.ext import commands
import time

class LeaderboardView(discord.ui.View):
    def __init__(self, bot, page, per_page):
        super().__init__(timeout=60)
        self.bot = bot
        self.page = page
        self.per_page = per_page

    async def get_page_embed(self, page):
        offset = (page - 1) * self.per_page
        rows = await self.bot.db.fetch(f'''
            SELECT user_id, count FROM nword_stats 
            ORDER BY count DESC LIMIT $1 OFFSET $2
        ''', self.per_page, offset)

        if not rows and page > 1: return None

        embed = discord.Embed(title=f"nword排行 (第 {page} 頁)", color=discord.Color.blue())
        desc = ""
        for i, row in enumerate(rows, 1 + offset):
            user_id = row['user_id']
            user = self.bot.get_user(user_id)
            if not user:
                try: user = await self.bot.fetch_user(user_id)
                except: user = None
            name = user.name if user else f"未知用戶({user_id})"
            desc += f"{i}. **{name}**: {row['count']:,} 次\n"
        
        embed.description = desc or "暫無資料"
        return embed

    @discord.ui.button(label="上一頁", style=discord.ButtonStyle.gray)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 1:
            self.page -= 1
            embed = await self.get_page_embed(self.page)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("已經是第一頁了", ephemeral=True)

    @discord.ui.button(label="下一頁", style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        next_embed = await self.get_page_embed(self.page + 1)
        if next_embed:
            self.page += 1
            await interaction.response.edit_message(embed=next_embed, view=self)
        else:
            await interaction.response.send_message("沒有下一頁了", ephemeral=True)

class WordCounter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_everyone_times = {}
        self.NWORDS_WEIGHTS = {
            "nigger": 1, "nigga": 1, "黑鬼": 1, "黑奴": 1, "nga": 1,
            "diddy": 2, "epstein": 7, "sybau": 3, "efn": 1, "niga": 1,
            "n1gga": 1, "幹": 1, "幹你娘": 2, "黑人": 1, "鞭": 1,
            "g8": 1, "黑鬼吃西瓜": 5, "閉嘴": 1, "滾": 1, "三小": 1,
            "靠北": 1, "你媽死了": 4, "你媽": 1, "cnm": 1,
        }

    async def handle_antispam(self, message):
        now = time.time()
        uid = message.author.id
        logs = self.user_everyone_times.get(uid, [])
        logs = [t for t in logs if now - t < 10]
        logs.append(now)
        self.user_everyone_times[uid] = logs
        try:
            await message.delete()
            if len(logs) == 2:
                await message.channel.send(f"{message.author.mention} 白痴被我防住了吧")
        except: pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not self.bot.db: return

        if "@everyone" in message.content or "@here" in message.content:
            await self.handle_antispam(message)
            return

        content_lower = message.content.lower()
        found_count = 0
        for word, weight in self.NWORDS_WEIGHTS.items():
            occ = content_lower.count(word)
            if occ > 0:
                found_count += (occ * weight)

        if found_count > 0:
            try:
                new_total = await self.bot.db.fetchval('''
                    INSERT INTO nword_stats (user_id, count)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET count = nword_stats.count + $2
                    RETURNING count
                ''', message.author.id, found_count)
                await message.channel.send(f"{message.author.mention}請不要說n字! 你已經說了 **{new_total:,}** 次")
            except Exception as e:
                print(f"DB Error: {e}")

    @commands.command(name="leaderboard", aliases=["lb"])
    async def leaderboard(self, ctx):
        if not self.bot.db: return
        view = LeaderboardView(self.bot, page=1, per_page=10)
        embed = await view.get_page_embed(1)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(WordCounter(bot))