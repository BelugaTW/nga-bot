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
        # 移除自定義 loop 傳遞，交由 run() 處理
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.db = None
        
    async def terminal_input(self):
        await self.wait_until_ready()
        print(">>> 終端機系統就緒 (頻道ID 訊息內容)")
        
        while not self.is_closed():
            try:
                user_input = await aioconsole.ainput("發送訊息 > ")
                if not user_input.strip(): continue
                
                parts = user_input.split(" ", 1)
                # 修正：過濾掉 VS Code 可能傳入的非數字前綴
                raw_id = "".join(filter(str.isdigit, parts[0]))
                
                if not raw_id or len(parts) < 2:
                    print("格式錯誤: 請輸入 [頻道ID] [訊息]")
                    continue
                
                channel_id = int(raw_id)
                message = parts[1]
                
                channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
                if channel:
                    await channel.send(message)
                    print(f"已發送至: {channel.name}")
                else:
                    print("錯誤: 找不到頻道")
            except Exception as e:
                print(f"輸入處理異常: {e}")

    async def setup_hook(self):
        # 1. 資料庫連線 (失敗不應該中斷 Cog 載入)
        try:
            self.db = await asyncpg.create_pool(
                user='postgres',
                password=os.getenv("DB_PASSWORD"),
                database='postgres',
                host='127.0.0.1'
            )
            print("Database connected")
        except Exception as e:
            print(f"Database error: {e}")
            # 不要在這裡 return，否則 Cog 都不會讀取

        # 2. 動態取得路徑，確保 Windows/Linux 都能讀到
        cogs_path = os.path.join(os.path.dirname(__file__), "cogs")
        
        if os.path.exists(cogs_path):
            for filename in os.listdir(cogs_path):
                if filename.endswith('.py') and not filename.startswith('__'):
                    extension = f'cogs.{filename[:-3]}'
                    try:
                        await self.load_extension(extension)
                        print(f"Loaded extension: {extension}")
                    except Exception as e:
                        print(f"Failed to load {extension}: {e}")
        else:
            print(f"警告: 找不到 cogs 資料夾，路徑為: {cogs_path}")
        
        self.loop.create_task(self.terminal_input())

    async def on_ready(self):
        print(f"Logged in as {self.user.name}")

if __name__ == "__main__":
    bot = MyBot()
    bot.run(os.getenv("DISCORD_TOKEN"))