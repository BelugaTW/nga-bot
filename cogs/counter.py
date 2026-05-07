from shutil import ignore_patterns

import discord
from discord import app_commands
from discord.ext import commands
import time
import re

class LeaderboardView(discord.ui.View):
    def __init__(self, bot, page, per_page):
        super().__init__(timeout=60)
        self.bot = bot
        self.page = page
        self.per_page = per_page

    async def get_page_embed(self, page):
        offset = (page - 1) * self.per_page
        if not self.bot.db: return None
        
        rows = await self.bot.db.fetch('''
            SELECT user_id, count FROM nword_stats 
            ORDER BY count DESC LIMIT $1 OFFSET $2
        ''', self.per_page, offset)

        if not rows and page > 1: return None

        embed = discord.Embed(title=f" 你們這些低能講幾次了 (第 {page} 頁)", color=discord.Color.gold())
        desc = ""
        for i, row in enumerate(rows, 1 + offset):
            user_id = row['user_id']
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            name = user.name if user else f"未知用戶({user_id})"
            desc += f"{i}. **{name}**: `{row['count']:,}` 次\n"
        
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
        self.NWORDS_WEIGHTS = {
            "nigger": 1, "nigga": 1, "黑鬼": 1, "黑奴": 1, 
            "diddy": 2, "epstein": 7, "sybau": 3, "niga": 1,
            "n1gga": 1, "幹你娘": 2, "黑人": 1, "鞭": 1,
            "g8": 1, "黑鬼吃西瓜": 5, "閉嘴": 1, "滾": 1, "三小": 1,
            "靠北": 1, "你媽死了": 4, "你媽": 1, "林秉諺": 69
            , "gay": 1, "你媽炸了": 4, "你媽死全家": 5, "你全家死了": 5, "尼哥": 1, 
            "尼哥吃西瓜": 5,"家人死完": 5, "全家死完": 5, "全家死了": 5, "你全家死完": 5
            }

    @commands.Cog.listener() 
    async def on_message(self, message):

        if message.author.bot or not message.content: 
            return

        # 2. 定義要排除的模式 (確保這是個 List [])
        ignore_patterns = [
            r'http[s]?://\S+',               # 網址
            r'\.(png|jpg|jpeg|gif|webp)$',    # 圖檔結尾
            r'cdn\.discordapp\.com',          # Discord 資源連結
            r'media\.discordapp\.net'         # Discord 媒體連結
        ]

        content_lower = message.content.lower()

        # 3. 檢查是否包含網址或圖片路徑
        for pattern in ignore_patterns:
            if re.search(pattern, content_lower):
                return # 命中排除模式，直接結束

        # 4. 排除附件
        if len(message.attachments) > 0:
            return
        clean_content = re.sub(r'[^\w\s]', '', content_lower)
        found_count = 0
        
        for word, weight in self.NWORDS_WEIGHTS.items():
            # 這裡多加一個判斷：確保關鍵字前後不是連結字元 (可選)
            occ = content_lower.count(word) or clean_content.count(word)
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
                await message.channel.send(f"{message.author.mention} 請不要說n字! 你已經說了 **{new_total:,}** 次")
            except Exception as e:
                print(f"DB Error: {e}")

    @app_commands.command(name="leaderboard", description="查看 nword 排行榜")
    async def leaderboard(self, interaction: discord.Interaction):
        if not self.bot.db:
            return await interaction.response.send_message("資料庫連線中...", ephemeral=True)
        
        await interaction.response.defer()
        view = LeaderboardView(self.bot, page=1, per_page=10)
        embed = await view.get_page_embed(1)
        
        if embed:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send("目前排行榜空空如也。")

async def setup(bot):
    await bot.add_cog(WordCounter(bot))
