import sqlite3
import gspread
from gspread_formatting import *
from oauth2client.service_account import ServiceAccountCredentials
import discord
import asyncio, pickle, time, os, sys
import stella_scraper

#constants
sheet_names = ['sl0', 'sl1', 'sl2', 'sl3', 'sl4', 'sl5', 'sl6', 'sl7', 'sl8', 'sl9', 'sl10', 'sl11', 'sl12', 'st0', 'st1', 'st2', 'st3', 'st4', 'st5', 'st6', 'st7', 'st8', 'st9', 'st10', 'st11', 'st12', 'dp0', 'dp1', 'dp2', 'dp3', 'dp4', 'dp5', 'dp6', 'dp7', 'dp8', 'dp9', 'dp10', 'dp11', 'dp12']
channel_id = 892431673822674944
admin_ids = [504114263070212097]
max_number_of_comments=20

def get_sheet_name(table_name, difficulty_number):
    if table_name=="st" or table_name=="sl" or table_name=="dp":
        return table_name+str(difficulty_number)
    else:
        raise ValueError


def get_difficulty(table_name, difficulty_number):
    if table_name=="st" or table_name=="sl":
        return table_name+str(difficulty_number)
    elif table_name=="dp":
        return "sl"+str(difficulty_number)
    else:
        raise ValueError

def get_table_name_and_difficulty(sheet_name):
    if sheet_name not in sheet_names:
        raise ValueError
    if sheet_name[:2]=="st":
        return ("st", sheet_name)
    if sheet_name[:2]=="sl":
        return ("sl", sheet_name)
    if sheet_name[:2]=="dp":
        return ("dp", "sl"+sheet_name[2:])


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Connect to DB
        self.db=sqlite3.connect("/home/nadchu/stella_bot/data.db", isolation_level=None)
        self.cur=self.db.cursor()
        self.db_ss=sqlite3.connect(":memory:", isolation_level=None) # for spreadsheet
        self.cur_ss=self.db_ss.cursor()
        self.cur_ss.execute("""
            create table song_location(
                table_name TEXT,
                chart_number INTEGER,
                sheet_name TEXT,
                row_number INTEGER,
                PRIMARY KEY(table_name, chart_number)
            )
        """)

        # Construct member_id_to_screenname dict
        self.member_id_to_screenname = dict()
        with open('/home/nadchu/stella_bot/member_id_to_screenname.pickle', 'rb') as f:
            self.member_id_to_screenname = pickle.load(f)

        # Get spreadsheet handler and fill
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        credentials = ServiceAccountCredentials.from_json_keyfile_name('/home/nadchu/stella_bot/stellabms-comment-c4fcf4b7a8c8.json', scope)
        self.spreadsheet_handler = gspread.authorize(credentials).open('Stellabms コメントまとめ')
        self.init_spreadsheet()

    async def on_ready(self):
        print(f'Logged on as {self.user}!', flush=True)

        async for message in self.get_channel(channel_id).history(limit=200):
            if message.author.bot:
                await message.delete()

    async def on_member_join(self, member):
        self.member_id_to_screenname[member.id]=member.name
        with open('/home/nadchu/stella_bot/member_id_to_screenname.pickle', 'wb') as f:
            pickle.dump(self.member_id_to_screenname, f)

    def change_member_name(self, member_id, member_name):
        self.member_id_to_screenname[member_id]=member_name
        with open('/home/nadchu/stella_bot/member_id_to_screenname.pickle', 'wb') as f:
            pickle.dump(self.member_id_to_screenname, f)

    async def on_message(self, message):
        content=message.content
        ind=content.find("> ")
        content=content[ind+2:]
        if self.user in message.mentions and not message.author.bot and message.channel.id==channel_id:
            if content.startswith("exit") and message.author.id in admin_ids:
                self.exit_code=1
                self.db.close()
                self.db_ss.close()
                await self.close()
                return
            elif content.startswith("restart") and message.author.id in admin_ids:
                self.exit_code=0
                self.db.close()
                self.db_ss.close()
                await self.close()
                return
            elif content.startswith("exec") and message.author.id in admin_ids:
                #Usage:  "exec print("Hello world!")"
                if len(content)>5:
                    toexec=content[5:]
                    print(f"> exec({toexec})", flush=True)
                    exec(toexec)
            else:
                if len(content.split("\n"))==1:
                    await message.channel.send(f"{message.author.mention} 投稿の解釈に失敗しました。1行目に楽曲情報を、2行目以降にコメントを記入して下さい。")
                    return

                comment_body=""
                for line in content.split("\n")[1:]:
                    comment_body+="\n"+line
                comment_body=comment_body[1:] # eliminate first char == "\n"

                line = content.split("\n")[0]

                for sheet_name in sheet_names:
                    if line.startswith(sheet_name+" "):
                        song_title=line.replace(sheet_name+" ", "")
                        table_name, difficulty = get_table_name_and_difficulty(sheet_name)
                        self.cur.execute("SELECT chart_number FROM charts WHERE is_collected=1 AND table_name=? AND difficulty=? AND title LIKE ?", (table_name, difficulty, f"%{song_title}%"))
                        candidates = self.cur.fetchall()
                        if len(candidates)==0:
                            await message.channel.send(f"{message.author.mention} 楽曲が見つかりませんでした…")
                            return
                        elif len(candidates)==1:
                            chart_number=candidates[0][0]
                            member_id=message.author.id
                            self.cur.execute("SELECT * FROM our_comments WHERE table_name=? AND chart_number=? AND member_id=?", (table_name, chart_number, member_id))
                            if self.cur.fetchone():
                                if comment_body=="削除":
                                    self.cur.execute("DELETE FROM our_comments WHERE table_name=? AND chart_number=? AND member_id=?", (table_name, chart_number, member_id))
                                    self.update_comments_on_spreadsheet(table_name, chart_number)
                                    await message.add_reaction("\U0001F4A5") # Collision
                                else: # Update comment
                                    self.cur.execute("UPDATE our_comments SET comment=? WHERE table_name=? AND chart_number=? AND member_id=?", (comment_body, table_name, chart_number, member_id))
                                    self.update_comments_on_spreadsheet(table_name, chart_number)
                                    await message.add_reaction("\U0001F199") # Up! Button
                            else:
                                if comment_body=="削除":
                                    await message.add_reaction("\U0001F4A5") # Collision
                                else: # New comment
                                    self.cur.execute("INSERT INTO our_comments VALUES (?, ?, ?, ?)", (table_name, chart_number, member_id, comment_body))
                                    self.update_comments_on_spreadsheet(table_name, chart_number)
                                    await message.add_reaction("\U0001F195") # New Button
                            return
                        else:
                            chart_numbers=[candidate[0] for candidate in candidates]
                            msg=f"{message.author.mention} 候補が複数あるため処理を中断しました。 (ID: "
                            for cn in chart_numbers:
                                msg+=str(cn)+", "
                            msg=msg[:-3]+")"
                            await message.channel.send(msg)
                            return
                await message.channel.send(f"{message.author.mention} 投稿の解釈に失敗しました。1行目に楽曲情報を、2行目以降にコメントを記入して下さい。")
                return


    def init_spreadsheet(self):
        first_row = [["ID","曲名","公式コメント"]]
        self.our_comment_col_offset = len(first_row[0]) # 3 cols offset

        for table_name in ["sl", "st", "dp"]:
            for difficulty_number in range(13):
                sheet_name = get_sheet_name(table_name, difficulty_number) # sheet_name is that of our spreadsheet
                difficulty = get_difficulty(table_name, difficulty_number) # difficulty_table_name can be found in stellabms URL
                print(f"Initializing sheet \"{sheet_name}\"", flush=True)
                self.cur.execute("SELECT chart_number, title, comment FROM charts WHERE is_collected=1 AND table_name=? AND difficulty=? ORDER BY title", (table_name, difficulty))
                db_data = self.cur.fetchall()
                sheet=self.spreadsheet_handler.worksheet(sheet_name)
                sheet.clear()
                sheet.update("A1", first_row) # update a range of cells using the top left corner address
                sheet.update("A2", db_data) # update a range of cells using the top left corner address
               #set_column_width(sheet, 'A', 65)
               #set_column_width(sheet, 'B:Z', 370)
               #sheet.format("A:Z", {
               #    "horizontalAlignment": "LEFT",
               #    "verticalAlignment": "MIDDLE"
               #})
               #sheet.format("B:Z", {
               #    "wrapStrategy": "WRAP"
               #})
               #time.sleep(5)
                comments=[["" for i in range(max_number_of_comments)] for j in range(len(db_data))]
                for row_number in range(len(db_data)):
                    chart_number = db_data[row_number][0]
                    self.cur_ss.execute("INSERT INTO song_location VALUES (?, ?, ?, ?)", (table_name, chart_number, sheet_name, row_number+2))
                    self.cur.execute("SELECT comment, member_id FROM our_comments WHERE table_name=? AND chart_number=?", (table_name, chart_number))
                    data=[]
                    for item in self.cur.fetchall():
                        data.append(list(item))
                    for i in range(len(data)):
                        comments[row_number][i]=data[i][0]+f"【{self.member_id_to_screenname[data[i][1]]}】"
                col_char=chr(ord("A")+self.our_comment_col_offset)
                row_char="2"
                sheet.update(col_char+row_char, comments)
                time.sleep(5)

    def update_comments_on_spreadsheet(self, table_name, chart_number):
        comments=[["" for i in range(max_number_of_comments)]]
        self.cur.execute("SELECT comment, member_id FROM our_comments WHERE table_name=? AND chart_number=?", (table_name, chart_number))
        data=self.cur.fetchall()
        for i in range(min(max_number_of_comments,len(data))):
            comments[0][i]=data[i][0]+f"【{self.member_id_to_screenname[data[i][1]]}】"
        self.cur_ss.execute("SELECT sheet_name, row_number FROM song_location WHERE table_name=? AND chart_number=?", (table_name, chart_number))
        data=self.cur_ss.fetchone()
        if data:
            sheet_name, row_number = data
            col_char=chr(ord("A")+self.our_comment_col_offset)
            sheet=self.spreadsheet_handler.worksheet(sheet_name)
            sheet.update(col_char+str(row_number), comments)

if __name__ == '__main__':
    exit_code=stella_scraper.update()
    if exit_code:
        print("Stellabms scraping failed. Terminate...", flush=True)
        sys.exit(1)
    else:
        with open('/home/nadchu/stella_bot/discord_token.txt', 'r') as f:
            token = f.read()
        intents = discord.Intents.default()
        intents.members = True
        discord_client = MyClient(intents=intents)
        discord_client.run(token, reconnect=False)
        sys.exit(discord_client.exit_code)
