import discord
from discord.ext import commands
from discord import app_commands
import asyncpg
import asyncio
import os
import aioconsole
from dotenv import load_dotenv
import random

# 加載環境變數
load_dotenv()

class MyBot(commands.Bot):
    def __init__(self):
        # 設定所有 Intents 確保能讀取訊息內容
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.db = None
        
    async def setup_hook(self):
        print("--- 正在啟動機器人系統 ---")
        
        # 1. 自動載入 cogs 資料夾下的所有模組
        if not os.path.exists('./cogs'):
            os.makedirs('./cogs')
            
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"已載入模組: {filename}")
                except Exception as e:
                    print(f"載入模組 {filename} 失敗: {e}")

        # 2. 資料庫連線 (10秒超時防止卡死)
        try:
            self.db = await asyncio.wait_for(asyncpg.create_pool(
                user='postgres',
                password=os.getenv("DB_PASSWORD"),
                database='postgres',
                host='127.0.0.1'
            ), timeout=10.0)
            print("資料庫連線成功")
        except Exception as e:
            print(f"資料庫連線跳過: {e}")

        # 3. 斜線指令同步 (同步到特定伺服器以便秒速生效)
        GUILD_ID = 1453038500743221478 
        target_guild = discord.Object(id=GUILD_ID)
        
        self.tree.copy_global_to(guild=target_guild)
        synced = await self.tree.sync(guild=target_guild)
        print(f"--- 🛠️ 同步完成！已註冊 {len(synced)} 個斜線指令 ---")

        # 啟動終端機輸入監聽
        self.loop.create_task(self.terminal_input())

    async def terminal_input(self):
        """讓你在 VS Code 終端機輸入 '頻道ID 訊息' 就能讓機器人說話"""
        await self.wait_until_ready()
        while True:
            try:
                user_input = await aioconsole.ainput("發送訊息 (格式: 頻道ID 內容) > ")
                parts = user_input.split(" ", 1)
                if len(parts) < 2: continue
                
                channel_id = int(parts[0])
                msg_content = parts[1]
                
                channel = self.get_channel(channel_id)
                if channel: 
                    await channel.send(msg_content)
                else:
                    print("找不到該頻道")
            except Exception as e:
                print(f"發送失敗: {e}")

# 初始化機器人物件
bot = MyBot()

@bot.event
async def on_ready():
    print(f"--- 機器人已上線: {bot.user.name} (ID: {bot.user.id}) ---")

@bot.event
async def on_message(message):
    # 排除機器人自己的訊息
    if message.author == bot.user:
        return

    content = message.content

    if "cl3" in content:
        await message.channel.send("好")

    if "1257204103973568624" in content:
        responses = ["是會誇我的好人", "是作者好朋友"]
        await message.channel.send(random.choice(responses))

    elif "1468930913684422795" in content:
        responses = ["hi", "你好", "叫你爹幹啥"]
        await message.channel.send(random.choice(responses))

    elif "871271188817661992" in content:
        responses = ["是福瑞", "可能是福瑞", "絕對是福瑞"]
        await message.channel.send(random.choice(responses))

    # 重要：處理完上述判斷後，讓指令（如 !play）可以繼續運作
    await bot.process_commands(message)

# 啟動機器人
bot.run(os.getenv("DISCORD_TOKEN"))