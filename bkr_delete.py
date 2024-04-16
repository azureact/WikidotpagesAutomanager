# -*- coding: utf-8 -*-

from tenacity import retry, stop_after_attempt, wait_fixed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import pyperclip as pc
import pickle
import json
import yaml
import time
import traceback
import requests
from datetime import datetime

pending_deleted_pages_info: dict[int, list] = {}
with open("deleted_pages.pkl", "rb") as file:
    pending_deleted_pages_info = pickle.load(file)

with open("config.yaml", "r") as f:
    config: dict = yaml.safe_load(f)
lowest_rated_link, bot_id, bot_password = config.values()

# 浏览器初始化
chrome_options = Options()
# chrome_options.add_argument('--headless') #无头浏览器
chrome_options.add_argument("blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
# chrome_options.add_argument('--proxy-server={}'.format('127.0.0.1:25565'))
chrome_options.add_argument("--ignore-certificate-errors")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
driver = webdriver.Chrome(options=chrome_options)
driver.implicitly_wait(5)


@retry(stop=stop_after_attempt(max_attempt_number=3), reraise=True, wait=wait_fixed(5))
def init_driver():
    driver.get("https://www.wikidot.com/default--flow/login__LoginPopupScreen")
    driver.find_element(By.NAME, "login").send_keys(bot_id)
    driver.find_element(By.NAME, "password").send_keys(bot_password)
    driver.find_element(
        By.XPATH,
        "//*[@id='html-body']/div[2]/div[2]/div/div[1]/div[1]/form/div[4]/div/button",
    ).click()


def type_check(element: str | None) -> str:
    if element is None:
        raise TypeError("Failed to get attributes.")
    else:
        return element


def edit_post(
    num: int, id: str, content: str, url: str | None = None, times: int = 5
):  # 编辑帖子
    for i in range(times):
        driver.refresh()
        try:
            driver.execute_script(
                f"WIKIDOT.modules.ForumViewThreadPostsModule.listeners.updateList({num})"
            )
            driver.execute_script(
                f'WIKIDOT.modules.ForumViewThreadModule.listeners.editPost(event,"{id[5:]}")'
            )
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "np-text"))
            )
            driver.find_element(By.ID, "np-text").clear()
            text = pc.paste()
            pc.copy(content)
            driver.find_element(By.ID, "np-text").send_keys(Keys.CONTROL, "v")
            pc.copy(text)
            driver.find_element(By.ID, "np-post").click()
            WebDriverWait(driver, 5).until_not(
                EC.presence_of_element_located((By.ID, "np-post"))
            )
            break
        except:
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "title modal-header")
                    )
                )
                if (
                    driver.find_element(By.CLASS_NAME, "title modal-header")
                    == "Permission error"
                    and url != None
                ):
                    deviant.append(
                        {
                            "page": num,
                            "id": id,
                            "content": content,
                            "url": url,
                            "error_type": "edit_post_permission",
                        }
                    )
                    break
            except:
                if i == times - 1 and url != None:
                    deviant.append(
                        {
                            "page": num,
                            "id": id,
                            "content": content,
                            "url": url,
                            "error_type": "edit_post_unknown",
                        }
                    )
    time.sleep(1)


def new_post(content: str, title: str, url: str | None = None, times: int = 5):
    for i in range(times):
        driver.refresh()
        try:
            driver.execute_script(
                "WIKIDOT.modules.ForumViewThreadModule.listeners.newPost(event,null)"
            )
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "np-title"))
            )
            driver.find_element(By.ID, "np-title").send_keys(title)
            driver.find_element(By.ID, "np-text").send_keys(content)
            driver.find_element(By.ID, "np-post").click()
            WebDriverWait(driver, 5).until_not(
                EC.presence_of_element_located((By.ID, "np-post"))
            )
            break
        except:
            if i == times - 1 and url != None:
                deviant.append(
                    {"content": content, "url": url, "error_type": "new_post"}
                )


def translate_delete(timer: float) -> str:  # 简写翻译删除文字
    return f"""
        由于翻译质量不佳，宣告删除。
        [[iframe https://timer.backroomswiki.cn/timer/time={timer*1000}/type=delete style="width: 400px; height: 65px;"]]"""


def normal_delete(score: int, timer: float) -> str:  # 简写正常删除文字
    return f"""
    由于条目的分数为{score}分，{"且距离发布时间已满1个月，" if score>-2 else ""}现根据[[[deletions-policy|删除政策]]]，宣告将删除此页：
    [[iframe https://timer.backroomswiki.cn/timer/time={timer*1000}/type=delete style="width: 400px; height: 65px;"]]
    如果你不是作者又想要重写该条目，请在此帖回复申请。请先取得作者的同意，并将原文的源代码复制至沙盒里。除非你是工作人员，否则请勿就申请重写以外的范围回复此帖。"""


@retry(stop=stop_after_attempt(max_attempt_number=3), reraise=True)
def find_post() -> list | None:  # 寻找删除宣告帖
    driver.refresh()
    try:
        num = range(
            1, int(driver.find_element(By.CLASS_NAME, "pager-no").text[10:]) + 1
        )
    except NoSuchElementException:
        num = range(1, 2)
    for i in num:
        driver.execute_script(
            f"WIKIDOT.modules.ForumViewThreadPostsModule.listeners.updateList({i})"
        )
        time.sleep(1)
        for j in driver.find_elements(By.CLASS_NAME, "post"):
            title = j.find_element(By.CLASS_NAME, "title").text
            if "职员" in title and "删除宣告" in title:
                return [i, j.get_attribute("id")]


@retry(
    stop=stop_after_attempt(max_attempt_number=3), reraise=True, wait=wait_fixed(0.5)
)
def add_tag(tag: str):  # 添加标签
    driver.find_element(By.ID, "tags-button").click()
    driver.find_element(By.ID, "page-tags-input").send_keys(tag)
    driver.find_element(By.XPATH, '//*[@id="action-area"]/div[2]/input[3]').click()
    time.sleep(1.5)


@retry(
    stop=stop_after_attempt(max_attempt_number=3), reraise=True, wait=wait_fixed(0.5)
)
def remove_tag(tag: str):  # 移除标签
    driver.find_element(By.ID, "tags-button").click()
    tags = type_check(
        driver.find_element(By.ID, "page-tags-input").get_attribute("value")
    ).replace(tag, "")
    driver.find_element(By.ID, "page-tags-input").clear()
    driver.find_element(By.ID, "page-tags-input").send_keys(tags)
    driver.find_element(By.XPATH, '//*[@id="action-area"]/div[2]/input[3]').click()
    time.sleep(1.5)


def add_original_pending_tag():
    driver.get(lowest_rated_link)
    page_list = []  # 为原创文章添加“待删除”
    for i in driver.find_element(
        By.XPATH, '//*[@id="page-content"]/div[1]/table/tbody'
    ).find_elements(By.TAG_NAME, "tr")[1:]:
        info = i.find_elements(By.TAG_NAME, "td")
        page_list.append(
            [
                info[0].find_element(By.TAG_NAME, "a").get_attribute("href"),
                int(
                    type_check(
                        info[4].find_element(By.TAG_NAME, "span").get_attribute("class")
                    )[11:21]
                ),
            ]
        )
    for url, release_time in page_list:
        driver.get(url + "/norender/true")
        driver.find_element(By.ID, "discuss-button").click()
        discuss = driver.current_url
        print(discuss)
        driver.get(url + "/norender/true")
        announce_time = time.time()
        score = int(driver.find_element(By.ID, "prw54355").text)
        page_id = driver.execute_script("return WIKIREQUEST.info.pageId;")
        print(page_id)
        if pending_deleted_pages_info.get(page_id) != None:
            del pending_deleted_pages_info[page_id]
        if announce_time - release_time >= 2678400:
            expected_deletion_time = 259200
        elif score <= -2:
            expected_deletion_time = 259200 if score > -10 else 86400
        else:
            continue
        add_tag(" 待删除 ")
        driver.get(discuss)
        if (post := find_post()) == None:
            new_post(
                normal_delete(score, announce_time + expected_deletion_time),
                "职员帖：删除宣告",
                discuss,
            )
        else:
            edit_post(
                post[0],
                post[1],
                normal_delete(score, announce_time + expected_deletion_time),
                discuss,
            )


def add_translate_pending_tags():
    driver.get(lowest_rated_link)  # 为翻译文章添加“待删除”
    for i in driver.find_element(
        By.XPATH, '//*[@id="page-content"]/div[4]/table/tbody'
    ).find_elements(By.TAG_NAME, "tr")[1:]:
        url = type_check(
            i.find_elements(By.TAG_NAME, "td")[0]
            .find_element(By.TAG_NAME, "a")
            .get_attribute("href")
        )
        driver.get(url + "/norender/true")
        driver.find_element(By.ID, "discuss-button").click()
        discuss = driver.current_url
        driver.get(url + "/norender/true")
        announce_time = time.time()
        page_id = driver.execute_script("return WIKIREQUEST.info.pageId;")
        if pending_deleted_pages_info.get(page_id) != None:
            del pending_deleted_pages_info[page_id]
        add_tag(" 待删除 ")
        driver.get(discuss)
        if (post := find_post()) == None:
            new_post(
                translate_delete((announce_time + 86400)), "职员帖：删除宣告", discuss
            )
        else:
            edit_post(
                post[0], post[1], translate_delete((announce_time + 86400)), discuss
            )


@retry(stop=stop_after_attempt(max_attempt_number=3), reraise=True)
def check_pending_pages():
    driver.get(lowest_rated_link)
    page_list = []  # 整理待删除文章
    for i in driver.find_element(
        By.XPATH, '//*[@id="page-content"]/div[2]/table/tbody'
    ).find_elements(By.TAG_NAME, "tr")[1:]:
        info = i.find_elements(By.TAG_NAME, "td")
        page_list.append(
            [
                info[0].find_element(By.TAG_NAME, "a").get_attribute("href"),
                int(
                    type_check(
                        info[4].find_element(By.TAG_NAME, "span").get_attribute("class")
                    )[11:21]
                ),
            ]
        )
    for url, release_time in page_list:
        driver.get(url + "/norender/true")
        score = int(driver.find_element(By.ID, "prw54355").text)
        title = driver.find_element(By.ID, "page-title").text
        original = bool(driver.find_elements(By.LINK_TEXT, "原创"))
        announce_time = time.time()
        page_id = driver.execute_script("return WIKIREQUEST.info.pageId;")
        driver.find_element(By.ID, "discuss-button").click()
        discuss = driver.current_url
        if (post := find_post()) != None:
            driver.execute_script(
                f"WIKIDOT.modules.ForumViewThreadPostsModule.listeners.updateList({post[0]})"
            )
            post_box = driver.find_element(By.ID, post[1])
            content = post_box.find_element(By.CLASS_NAME, "content").text
            if "分数回升" in content:
                driver.get(url + "/norender/true")
                remove_tag("待删除")
                continue
            timer_link = type_check(
                post_box.find_element(By.TAG_NAME, "iframe").get_attribute("src")
            )
            if "arandintday.github.io" in timer_link:
                record_timestamp = (
                    float(
                        timer_link[
                            timer_link.find("?timestamp=")
                            + 11 : timer_link.find("&type=0")
                        ]
                    )
                    / 1000
                )
            elif ".000Z" in timer_link:
                record_timestamp = datetime.fromisoformat(
                    timer_link[
                        timer_link.find("/timer/time=") + 12 : timer_link.find(".000Z")
                    ]
                ).timestamp()
            else:
                record_timestamp = (
                    float(
                        timer_link[
                            timer_link.find("/timer/time=")
                            + 12 : timer_link.find("/type=")
                        ]
                    )
                    / 1000
                )
            print(record_timestamp)
            try:
                page_score = int(
                    content[content.find("条目的分数为") + 6 : content.find("分，")]
                )
            except ValueError:
                if original:
                    record_timestamp = announce_time + 259200
                    edit_post(
                        post[0],
                        post[1],
                        normal_delete(score, record_timestamp),
                        discuss,
                    )
                    page_score = -2
                else:
                    page_score = (
                        score
                        if pending_deleted_pages_info.get(page_id) == None
                        else pending_deleted_pages_info[page_id][0]
                    )
            if page_score <= -10 and record_timestamp < announce_time + 259200:
                basic_timestamp = (
                    pending_deleted_pages_info[page_id][1]
                    if pending_deleted_pages_info.get(page_id) != None
                    else record_timestamp + 172800
                )
            else:
                basic_timestamp = record_timestamp
            pending_deleted_pages_info[page_id] = [
                page_score,
                basic_timestamp,
                post[0],
                post[1],
                url,
            ]
        else:
            driver.get(url + "/norender/true")
            remove_tag("待删除")
            continue
        if (
            (score > -2 and announce_time - release_time < 2678400 and original)
            or score >= 5
            or (not original and score >= 0)
        ):  # 取消删除
            edit_post(
                pending_deleted_pages_info[page_id][2],
                pending_deleted_pages_info[page_id][3],
                "【分数回升，倒计时停止】",
                discuss,
            )
            driver.get(url + "/norender/true")
            remove_tag("待删除")
            del pending_deleted_pages_info[page_id]
        elif (
            pending_deleted_pages_info[page_id][0] <= -10 and score > -10 and original
        ):  # 24h->72h
            pending_deleted_pages_info[page_id][0] = score
            edit_post(
                pending_deleted_pages_info[page_id][2],
                pending_deleted_pages_info[page_id][3],
                normal_delete(score, pending_deleted_pages_info[page_id][1]),
                discuss,
            )
        elif (
            score <= -10
            and pending_deleted_pages_info[page_id][0] > -10
            and pending_deleted_pages_info[page_id][1] - announce_time > 86400
        ):  # 72h->24h
            pending_deleted_pages_info[page_id][0] = score
            edit_post(
                pending_deleted_pages_info[page_id][2],
                pending_deleted_pages_info[page_id][3],
                normal_delete(score, announce_time + 86400),
                discuss,
            )
        if announce_time >= record_timestamp:
            pending_delete_list.append(
                [
                    url,
                    pending_deleted_pages_info[page_id][0],
                    "normal" if original else "translate",
                ]
            )  # 加入pending_delete_list
        elif pending_deleted_pages_info.get(page_id) != None:
            pending_delete_pages.append(
                {
                    "link": url,
                    "title": title,
                    "score": score,
                    "release_score": page_score,
                    "time": 72 if page_score > -10 else 24,
                    "discuss_link": discuss,
                    "post_page": post[0],
                    "post_id": post[1],
                    "isOriginal": original,
                    "timestamp": record_timestamp,
                }
            )
        if score <= -30:
            pending_delete_list.append(
                [url, pending_deleted_pages_info[page_id][0], "minusThirty"]
            )


def add_deleted_category():
    driver.get(lowest_rated_link)
    for i in driver.find_element(
        By.XPATH, '//*[@id="page-content"]/div[3]/table/tbody'
    ).find_elements(By.TAG_NAME, "tr")[1:]:
        info = i.find_elements(By.TAG_NAME, "td")
        url = info[0].find_element(By.TAG_NAME, "a").get_attribute("href")
        score = int(info[1].find_element(By.TAG_NAME, "span").text)
        pending_delete_list.append([url, score, "deleted"])


def check_pending_deleted_pages_info():
    for i in list(
        pending_deleted_pages_info.keys()
    ):  # 删除pending_deleted_pages_info中的无效页面
        driver.get(pending_deleted_pages_info[i][4] + "/norender/true")
        try:
            driver.find_element(By.ID, "more-options-button")
        except NoSuchElementException:
            del pending_deleted_pages_info[i]
    print(pending_deleted_pages_info)


@retry(stop=stop_after_attempt(max_attempt_number=3), reraise=True)
def generate_announce():
    for url, release_score, page_type in pending_delete_list:  # 检验删除宣告
        index = -1
        for j, value in enumerate(js_result):
            if value["link"] == url:
                index = j
                break
        if index == -1:
            driver.get(url + "/norender/true")
            title = driver.find_element(By.ID, "page-title").text
            score = int(driver.find_element(By.ID, "prw54355").text)
            driver.find_element(By.ID, "more-options-button").click()
            driver.find_element(By.ID, "view-source-button").click()
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "page-source"))
            )
            context = driver.find_element(By.CLASS_NAME, "page-source").text
            js_result.append(
                {
                    "link": url,
                    "title": title,
                    "score": score,
                    "release_score": release_score,
                    "time": (
                        24 if release_score <= -10 or page_type == "translate" else 72
                    ),
                    "context": context,
                    "page_type": [page_type],
                }
            )
        else:
            if page_type == "normal":
                js_result[index]["release_score"] = release_score
            js_result[index]["page_type"] += [page_type]


def main():
    global pending_delete_list, pending_delete_pages, deviant, js_result
    deviant = []  # 错误信息
    js_result = []  # 自删页面，低分翻译页面-30，以下页面，-30~+5页面相关信息
    pending_delete_list = []  # 待检验页面
    pending_delete_pages = []  # 在倒计时中的页面
    add_original_pending_tag()
    add_translate_pending_tags()
    check_pending_pages()
    add_deleted_category()
    check_pending_deleted_pages_info()
    with open("deleted_pages.pkl", "wb") as file:
        pickle.dump(pending_deleted_pages_info, file)
    print(pending_delete_list)
    generate_announce()
    with open("data.json", "w") as json_file:
        json.dump(
            {
                "pre_delete_pages": pending_delete_pages,
                "deleted_pages": js_result,
                "errors": deviant,
                "update_timestamp": time.time(),
            },
            json_file,
        )


if __name__ == "__main__":
    init_driver()
    flag = 0
    while flag < 5:
        try:
            response = requests.get(lowest_rated_link)
            if response.status_code == 200:
                main()
                time.sleep(1800)
                flag = 0
            else:
                time.sleep(10)
        except Exception as e:
            flag += 1
            traceback.print_exc()
            time.sleep(3)

driver.close()