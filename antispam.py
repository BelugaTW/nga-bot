import discord
from discord.ext import commands
import asyncpg
import asyncio
import os
import aioconsole
from dotenv import load_dotenv

load_dotenv() 

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.db = None
        
    async def terminal_input(self):
        await self.wait_until_ready()
        print("終端機訊息系統已就緒 (格式: 頻道ID 訊息內容)")
        
        while True:
            user_input = await aioconsole.ainput("發送訊息 > ")
            try:
                parts = user_input.split(" ", 1)
                if len(parts) < 2:
                    print("格式錯誤，請輸入: 頻道ID 訊息內容")
                    continue
                
                channel_id, message = int(parts[0]), parts[1]
                channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
                
                if channel:
                    await channel.send(message)
                    print(f"成功發送至 {channel.name}")
                else:
                    print("找不到該頻道")
            except Exception as e:
                print(f"發送失敗: {e}")

    async def setup_hook(self):
        try:
            self.db = await asyncpg.create_pool(
                user='postgres',
                password = os.getenv("DB_PASSWORD"),
                database='postgres',
                host='127.0.0.1'
            )
            print("資料庫連線成功")
        except Exception as e:
            print(f"連線失敗: {e}")
            return

        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        
        self.loop.create_task(self.terminal_input())


bot = MyBot()
bot.run(os.getenv("DISCORD_TOKEN"))
