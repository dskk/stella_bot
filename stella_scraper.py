import chromedriver_binary
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
import sqlite3
import time, sys

class chart_info:
    def __init__(self):
        self.table_name = None # "st" or "sl"
        self.chart_number = None
        self.is_collected = 0
        # from stella web page
        self.difficulty = None
        self.title = None
        self.song_url = None
        self.chart_url = None
        self.lr2ir = None
        self.minir = None
        self.proposer = None
        self.comment = None
        self.proposal_date = None
        self.vote = None
        self.status = None

    def make_tuple(self):
        return (
            self.table_name,
            self.chart_number,
            self.is_collected,
            self.difficulty,
            self.title,
            self.song_url,
            self.chart_url,
            self.lr2ir,
            self.minir,
            self.proposer,
            self.comment,
            self.proposal_date,
            self.vote,
            self.status
        )

# globals
cur = None
driver = None

# constants
valid_difficulty_table_names = ["st", "sl", "dp"]

def get_chart_info_by_number(difficulty_table_name, number):
    if difficulty_table_name in valid_difficulty_table_names:
        url=f"https://stellabms.xyz/s/{difficulty_table_name}/{number}"
    else:
        raise ValueError(f"Invalid difficulty table name: {difficulty_table_name}")
    return get_chart_info_by_url(url)

def get_chart_info_by_url(url):
    info = chart_info()
    try:
        driver.get(url)
        driver.implicitly_wait(5)
        bs=BeautifulSoup(driver.find_element_by_class_name("framed").get_attribute("innerHTML"),"html.parser")
        difficulty_table_name, chart_number = url.split("/")[-2:]
        info.table_name=difficulty_table_name
        info.chart_number=chart_number
        difficulty, title = bs.select("h1")[0].text.split("\xa0")
        info.difficulty=difficulty
        info.title=title
        chart_raw_info=list(zip(bs.select("th"), bs.select("td"))) # [n][2] list
        for i in range(len(chart_raw_info)):
            key, val = chart_raw_info[i]
            key=key.text
            if key != "Proposer" and val.find("a") and val.find("a").get("href"):
                val=str(val.find("a").get("href"))
            else:
                val=val.text
                if val==None:
                    val=""
            if key == "Song URL":
                info.song_url=val
            elif key == "Chart URL":
                info.chart_url=val
            elif key ==  "LR2IR":
                info.lr2ir=val
            elif key ==  "MinIR":
                info.minir=val
            elif key ==  "Proposer":
                info.proposer=val
            elif key ==  "Comment":
                info.comment=val
            elif key ==  "Proposal Date":
                info.proposal_date=val
            elif key ==  "Vote":
                info.vote=val
            elif key == "Status": # (Accept, Reject, Canceled, New)
                info.status=val
        return info
    except NoSuchElementException:
        # Chart page does not exist
        info.status="Invalid"
        return info
    except Exception:
        # Resubmit exceptions other than NoSuchElementException
        raise


def get_update_info_by_number(difficulty_table_name, number):
    if difficulty_table_name in valid_difficulty_table_names:
        url=f"https://stellabms.xyz/u/{difficulty_table_name}/{number}"
    else:
        raise ValueError(f"Invalid difficulty table name: {difficulty_table_name}")
    return get_update_info_by_url(url)

def get_update_info_by_url(url):
    try:
        driver.get(url)
        driver.implicitly_wait(5)
        bs=BeautifulSoup(driver.find_element_by_class_name("framed").get_attribute("innerHTML"),"html.parser")
        if bs.find("td",class_="result-new"):
            return "New"
        for a_tag in bs.find_all("a"):
            href=a_tag.get("href")
            if href.startswith("/s/"):
                return "https://stellabms.xyz"+href
        raise Exception("Chart update page parse error")
    except NoSuchElementException:
        # Chart page does not exist
        return "Invalid"
    except Exception:
        # Resubmit exceptions other than NoSuchElementException
        raise

def reflect_difficulty_table(difficulty_table_name, cur):
    if difficulty_table_name in valid_difficulty_table_names:
        url=f"https://stellabms.xyz/{difficulty_table_name}/table.html"
    else:
        raise ValueError(f"Invalid difficulty table name: {difficulty_table_name}")
    driver.get(url)
    time.sleep(5)
    bs=BeautifulSoup(driver.page_source,"html.parser")
    entries=bs.findAll("tr")[1:] # 1行目は要らない
    for entry in entries:
        if len(entry)==1: # 見出しは使わない
            continue
        entry=entry.contents
        chart_number = int(entry[4].a["href"].split("/")[-1])
        difficulty=entry[0].text #難易度
        cur.execute("UPDATE charts SET difficulty=?, is_collected=1 WHERE table_name=? AND chart_number=?",(difficulty, difficulty_table_name, chart_number))


def get_incoming_chart_info(difficulty_table_name, start_number, cur):
    invalid_count=0 # count consecutive invalid pages
    start_number_for_next_run=-1 # -1 means unset
    number=start_number
    while True:
        cur.execute("SELECT * FROM charts WHERE table_name=? AND chart_number=?", (difficulty_table_name, number))
        if cur.fetchone():
            print(f"Chart info {difficulty_table_name}_{number} is already fetched.", flush=True)
            number+=1
            continue
        print(f"Fetching chart info: {difficulty_table_name}_{number}.", flush=True)
        info = get_chart_info_by_number(difficulty_table_name, number)
        if info.status=="New":
            invalid_count=0
            print(f"Vote for new chart {difficulty_table_name}_{number} is ongoing. Skipped.", flush=True)
            if start_number_for_next_run==-1: # start from oldest "New" chart next time
                start_number_for_next_run=number
        elif info.status=="Invalid":
            print(f"Chart info page {difficulty_table_name}_{number} does not exist or parse error.", flush=True)
            invalid_count+=1
        elif info.status=="Accept" or info.status=="Reject" or info.status=="Canceled":
            invalid_count=0
            cur.execute("INSERT INTO charts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", info.make_tuple())
            print(f"Inserted chart info: {difficulty_table_name}_{number} = {info.make_tuple()}", flush=True)
        else:
            raise Exception(f"Chart info parse error {difficulty_table_name}_{number}: {info.make_tuple()}")
        if invalid_count==5:
            if start_number_for_next_run==-1:
                start_number_for_next_run=number-4
            break
        number+=1
    return start_number_for_next_run

def get_incoming_update_info(difficulty_table_name, start_number, cur):
    invalid_count=0 # count consecutive invalid pages
    start_number_for_next_run=-1 # -1 means unset
    number=start_number
    while True:
        cur.execute("SELECT * FROM processed_updates WHERE table_name=? AND update_number=?", (difficulty_table_name, number))
        if cur.fetchone():
            print(f"Update info {difficulty_table_name}_{number} is already fetched.", flush=True)
            number+=1
            continue
        print(f"Fetching update info: {difficulty_table_name}_{number}.", flush=True)
        retval = get_update_info_by_number(difficulty_table_name, number)
        if retval=="New":
            invalid_count=0
            print(f"Vote for chart update {difficulty_table_name}_{number} is ongoing. Skipped.", flush=True)
            if start_number_for_next_run==-1: # start from oldest "New" chart next time
                start_number_for_next_run=number
        elif retval=="Invalid":
            print(f"Update info page {difficulty_table_name}_{number} does not exist or parse error.", flush=True)
            invalid_count+=1
        else: # retval is URL
            invalid_count=0
            info = get_chart_info_by_url(retval)
            cur.execute("UPDATE charts SET difficulty=?, status=? WHERE table_name=? AND chart_number=?",(info.difficulty, info.status, difficulty_table_name, number))
            cur.execute("INSERT INTO processed_updates VALUES (?, ?)", (difficulty_table_name, number))
            print(f"Updated chart info: {difficulty_table_name}_{number} = {info.make_tuple()}", flush=True)
        if invalid_count==5:
            if start_number_for_next_run==-1:
                start_number_for_next_run=number-4
            break
        number+=1
    return start_number_for_next_run

def update():
    global cur, driver
    db = sqlite3.connect("/home/nadchu/stella_bot/data.db")
    cur = db.cursor()

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    #options.add_argument('--lang=en')
    #options.add_experimental_option('prefs', {'intl.accept_languages': 'en, en_US'}) # locale=en_US
    driver = webdriver.Chrome('chromedriver', options=options)
    driver.set_page_load_timeout(30)

    try:
        cur.execute("SELECT * FROM update_log ORDER BY log_id DESC")
        log_id, log_date, st_chart_start, st_update_start, sl_chart_start, sl_update_start, dpsl_chart_start, dpsl_update_start = cur.fetchone() # get last log
        print(f"* Loaded update log. log_id={log_id}.", flush=True)

        # 新規提案の取得
        print("* Start fetching incoming chart proposals [st]", flush=True)
        st_chart_start = get_incoming_chart_info("st", st_chart_start, cur)
        print("* Start fetching incoming chart proposals [sl]", flush=True)
        sl_chart_start = get_incoming_chart_info("sl", sl_chart_start, cur)
        print("* Start fetching incoming chart proposals [dpsl]", flush=True)
        dpsl_chart_start = get_incoming_chart_info("dp", dpsl_chart_start, cur)
        db.commit()

        # 修正提案の取得
        print("* Start fetching incoming chart updates [st]", flush=True)
        st_update_start = get_incoming_update_info("st", st_update_start, cur)
        print("* Start fetching incoming chart updates [sl]", flush=True)
        sl_update_start = get_incoming_update_info("sl", sl_update_start, cur)
        print("* Start fetching incoming chart updates [dpsl]", flush=True)
        dpsl_update_start = get_incoming_update_info("dp", dpsl_update_start, cur)
        db.commit()

        # 難度表情報の取得
        print("* Start reflecting difficulty table data.", flush=True)
        cur.execute("UPDATE charts SET is_collected=0")
        reflect_difficulty_table("st", cur)
        reflect_difficulty_table("sl", cur)
        reflect_difficulty_table("dp", cur)

        cur.execute("INSERT INTO update_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (log_id+1, time.strftime("%Y-%m-%d %H:%M:%S"), st_chart_start, st_update_start, sl_chart_start, sl_update_start, dpsl_chart_start, dpsl_update_start))

        print("* Stellabms scraping done!", flush=True)
        db.commit()
        db.close()
        driver.quit()
        return 0

    except Exception as e:
        print(e, file=sys.stderr)
        db.close()
        driver.quit()
        return 1

