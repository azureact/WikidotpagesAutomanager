# -*- coding: utf-8 -*-

from tenacity import retry, stop_after_attempt, wait_fixed, after_log
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
import sys
import requests
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler(f"logs/{datetime.now().strftime('%Y-%m-%d')}.txt")
console_handler.setLevel(logging.INFO)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addHandler(file_handler)


with open("deleted_pages.pkl", "rb") as file:
    pending_deleted_pages_info: dict[int, list] = pickle.load(file)
logger.info(f'载入历史数据：{pending_deleted_pages_info}')

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
logger.info('Chrome浏览器启动！')


@retry(stop=stop_after_attempt(max_attempt_number=3), reraise=True, wait=wait_fixed(5))
def init_driver():
    driver.get("https://www.wikidot.com/default--flow/login__LoginPopupScreen")
    logger.info(f"正在使用账号 {bot_id} 登录")
    driver.find_element(By.NAME, "login").send_keys(bot_id)
    driver.find_element(By.NAME, "password").send_keys(bot_password)
    driver.find_element(
        By.XPATH,
        "//*[@id='html-body']/div[2]/div[2]/div/div[1]/div[1]/form/div[4]/div/button",
    ).click()
    logger.info("登录操作完成")


def cut(text:str, index1:str, index2:str, offset1:int = 0, offset2:int = 0) -> str:
    return text[text.find(index1) + len(index1) + offset1:text.find(index2) + offset2]


def get_page_list(num:int)->list:
    page_list = []  # 整理待删除文章
    for i in driver.find_element(
        By.XPATH, f'//*[@id="page-content"]/div[{num}]/table/tbody'
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
    logger.debug(f'已获取第{num}个表格的文章数据')
    return page_list

def type_check(element: str | None) -> str:
    if element is None:
        raise TypeError("Failed to get attributes.")
    else:
        return element


def edit_post(num: int, id: str, content: str, url: str | None = None, times: int = 5) -> bool:  # 编辑帖子
    logger.info(f'准备编辑{url + "中" if url is not None else ""}第{num}页，id为{id}帖子')
    for i in range(times):
        driver.refresh()
        try:
            driver.execute_script(
                f"WIKIDOT.modules.ForumViewThreadPostsModule.listeners.updateList({num})"
            )
            driver.execute_script(
                f'WIKIDOT.modules.ForumViewThreadModule.listeners.editPost(event,"{id[5:]}")'
            )
            logger.debug(f'定位至位于第{num}页，id为{id}帖子')
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
            logger.info(f'第{num}页，id为{id}帖子编辑完成')
            return True
        except:
            logger.warning(f'第{i+1}/{times}次编辑帖子失败')
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "title modal-header")
                    )
                )
                if (
                    driver.find_element(By.CLASS_NAME, "title modal-header")
                    == "Permission error"
                    and url is not None
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
                    logger.error(f'编辑第{num}页，id为{id}帖子时遇到权限错误，中断重试')
                    return False
            except:
                if i == times - 1 and url is not None:
                    deviant.append(
                        {
                            "page": num,
                            "id": id,
                            "content": content,
                            "url": url,
                            "error_type": "edit_post_unknown",
                        }
                    )
                    logger.error(f'编辑第{num}页，id为{id}帖子时遇到未知错误，放弃重试')
    return False


def new_post(content: str, title: str, url: str | None = None, times: int = 5) -> bool:
    logger.info(f'准备{"在"+ url + "中" if url is not None else ""}新建帖子')
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
            logger.info('帖子新建完成')
            return True
        except:
            logger.warning(f'第{i+1}/{times}次新建帖子失败')
            if i == times - 1 and url is not None:
                deviant.append(
                    {"content": content, "url": url, "error_type": "new_post"}
                )
                logger.error(f'新建帖子时遇到未知错误，放弃重试')
    return False


def translate_delete(timer: float) -> str:  # 简写翻译删除文字
    return f"""
        由于翻译质量不佳，宣告删除。
        [[iframe https://timer.backroomswiki.cn/timer/time={timer*1000}/type=delete style="width: 400px; height: 65px;"]]"""


def normal_delete(score: int, timer: float) -> str:  # 简写正常删除文字
    return f"""
    由于条目的分数为{score}分，{"且距离发布时间已满1个月，" if score>-2 else ""}现根据[[[deletions-policy|删除政策]]]，宣告将删除此页：
    [[iframe https://timer.backroomswiki.cn/timer/time={timer*1000}/type=delete style="width: 400px; height: 65px;"]]
    如果你不是作者又想要重写该条目，请在此帖回复申请。请先取得作者的同意，并将原文的源代码复制至沙盒里。除非你是工作人员，否则请勿就申请重写以外的范围回复此帖。"""


def find_post(times:int=3) -> list | None:  # 寻找删除宣告帖
    for i in range(times):
        try:
            logger.debug('尝试寻找删除宣告帖')
            driver.refresh()
            try:
                logger.debug('获取页码数量')
                num = range(
                    1, int(driver.find_element(By.CLASS_NAME, "pager-no").text[10:]) + 1
                )
            except NoSuchElementException:
                logger.debug('页码数量检测到为1')
                num = range(1, 2)
            for i in num:
                driver.execute_script(
                    f"WIKIDOT.modules.ForumViewThreadPostsModule.listeners.updateList({i})"
                )
                WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "post"))
                    )
                logger.info(f'在第{i}页寻找删除宣告帖')
                for j in driver.find_elements(By.CLASS_NAME, "post"):
                    title = j.find_element(By.CLASS_NAME, "title").text
                    id=j.get_attribute("id")
                    if "职员" in title and "删除宣告" in title:
                        logger.info(f'在第{i}页找到删除宣告，id为{id}')
                        return [i, id]
        except:
            logger.info(f'第{i}次尝试未找到删除宣告帖')
    logger.warning('达到最大尝试次数，放弃寻找删除帖')


@retry(stop=stop_after_attempt(max_attempt_number=5), reraise=True, wait=wait_fixed(0.5), after=after_log(logger, log_level=logging.WARNING))
def add_tag(tag: str):  # 添加标签
    logger.info(f'发起尝试添加{tag}标签')
    driver.find_element(By.ID, "tags-button").click()
    driver.find_element(By.ID, "page-tags-input").send_keys(tag)
    driver.find_element(By.XPATH, '//*[@id="action-area"]/div[2]/input[3]').click()
    logger.info('标签添加完成')
    time.sleep(1.5)


@retry(stop=stop_after_attempt(max_attempt_number=5), reraise=True, wait=wait_fixed(0.5), after=after_log(logger, log_level=logging.WARNING))
def remove_tag(tag: str):  # 移除标签
    logger.info(f'发起尝试移除{tag}标签')
    driver.find_element(By.ID, "tags-button").click()
    tags = type_check(
        driver.find_element(By.ID, "page-tags-input").get_attribute("value")
    ).replace(tag, "")
    driver.find_element(By.ID, "page-tags-input").clear()
    driver.find_element(By.ID, "page-tags-input").send_keys(tags)
    driver.find_element(By.XPATH, '//*[@id="action-area"]/div[2]/input[3]').click()
    logger.info('标签移除完成')
    time.sleep(1.5)

@retry(stop=stop_after_attempt(max_attempt_number=5), reraise=True, after=after_log(logger, log_level=logging.WARNING))
def add_original_pending_tag(page:list):
    url, release_time = page
    logger.info(f'访问页面{url}')
    driver.get(url + "/norender/true")
    announce_time = time.time()
    score = int(driver.find_element(By.ID, "prw54355").text)
    page_id = driver.execute_script("return WIKIREQUEST.info.pageId;")
    if pending_deleted_pages_info.get(page_id) is not None:
        logger.info('移除pending_deleted_pages_info中的残余数据')
        del pending_deleted_pages_info[page_id]
    if announce_time - release_time >= 2678400:
        expected_deletion_time = 259200
    elif score <= -2:
        expected_deletion_time = 259200 if score > -10 else 86400
    else:
        logger.info('页面分数不满足删除条件，跳过此页面')
        return
    driver.find_element(By.ID, "discuss-button").click()
    discuss = driver.current_url
    logger.debug(f'获取讨论区链接{discuss}')
    logger.info('前往讨论区发布删除宣告')
    flag = False
    if (post := find_post()) is None:
        flag = new_post(
            normal_delete(score, announce_time + expected_deletion_time),
            "职员帖：删除宣告",
            discuss,
        )
    else:
        flag = edit_post(
            post[0],
            post[1],
            normal_delete(score, announce_time + expected_deletion_time),
            discuss,
        )
    if flag:
        driver.get(url + "/norender/true")
        add_tag(" 待删除 ")

@retry(stop=stop_after_attempt(max_attempt_number=5), reraise=True, after=after_log(logger, log_level=logging.WARNING))
def add_translate_pending_tag(url:str):
    driver.get(url + "/norender/true")
    logger.info(f'访问页面{url}')
    announce_time = time.time()
    page_id = driver.execute_script("return WIKIREQUEST.info.pageId;")
    if pending_deleted_pages_info.get(page_id) is not None:
        logger.info('移除pending_deleted_pages_info中的残余数据')
        del pending_deleted_pages_info[page_id]
    driver.find_element(By.ID, "discuss-button").click()
    discuss = driver.current_url
    logger.debug(f'获取讨论区链接{discuss}')
    logger.info('前往讨论区发布删除宣告')
    flag = False
    if (post := find_post()) is None:
        flag = new_post(
            translate_delete((announce_time + 86400)), "职员帖：删除宣告", discuss
        )
    else:
        flag = edit_post(
            post[0], post[1], translate_delete((announce_time + 86400)), discuss
        )
    if flag:
        driver.get(url + "/norender/true")
        add_tag(" 待删除 ")

@retry(stop=stop_after_attempt(max_attempt_number=5), reraise=True, after=after_log(logger, log_level=logging.WARNING))
def check_pending_pages(page:list):
    url,release_time = page
    driver.get(url + "/norender/true")
    logger.info(f'访问{url}')
    score = int(driver.find_element(By.ID, "prw54355").text)
    title = driver.find_element(By.ID, "page-title").text
    original = bool(driver.find_elements(By.LINK_TEXT, "原创"))
    announce_time = time.time()
    page_id = driver.execute_script("return WIKIREQUEST.info.pageId;")
    driver.find_element(By.ID, "discuss-button").click()
    discuss = driver.current_url
    logger.debug(f'获取讨论区链接{discuss}')
    if (post := find_post()) is not None:
        driver.execute_script(
            f"WIKIDOT.modules.ForumViewThreadPostsModule.listeners.updateList({post[0]})"
        )
        WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.ID, post[1]))
            )
        post_box = driver.find_element(By.ID, post[1])
        content = post_box.find_element(By.CLASS_NAME, "content").text
        if "分数回升" in content:
            driver.get(url + "/norender/true")
            remove_tag("待删除")
            logger.info("检测到删除宣告内容为分数回升，跳过页面")
            return
        timer_link = type_check(
            post_box.find_element(By.TAG_NAME, "iframe").get_attribute("src")
        )
        if "arandintday.github.io" in timer_link:
            record_timestamp = float(cut(timer_link,"?timestamp=","&type=0"))/ 1000
        elif ".000Z" in timer_link:
            record_timestamp = datetime.fromisoformat(cut(timer_link,"/timer/time=",".000Z")).timestamp()
        else:
            record_timestamp = float(cut(timer_link,"/timer/time=","/type="))/ 1000
        logger.debug(f'删除宣告时间戳为{record_timestamp}')
        try:
            page_score = int(cut(content, "条目的分数为","分，"))
            logger.debug('检测到删除宣告为原创文章')
        except ValueError:
            logger.debug('检测到删除宣告为翻译文章')
            if original:
                logger.info('文章为原创文章但使用翻译文章的删除宣告，准备重置删除宣告')
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
                    if pending_deleted_pages_info.get(page_id) is None
                    else pending_deleted_pages_info[page_id][0]
                )
        if page_score <= -10 and record_timestamp < announce_time + 259200:
            basic_timestamp = (
                pending_deleted_pages_info[page_id][1]
                if pending_deleted_pages_info.get(page_id) is not None
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
        logger.info(f'{url}的页面信息保存完成')
    else:
        driver.get(url + "/norender/true")
        remove_tag("待删除")
        logger.info('跳过页面')
        return
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
        logger.info('文章分数回升，取消删除并删除页面信息')
    elif (
        pending_deleted_pages_info[page_id][0] <= -10 and score > -10 and original
    ):  # 24h->72h
        logger.info(f'将文章{url}的删除宣告倒计时从24小时修改为72小时，当前分数为{score}')
        pending_deleted_pages_info[page_id][0] = score
        edit_post(
            pending_deleted_pages_info[page_id][2],
            pending_deleted_pages_info[page_id][3],
            normal_delete(score, record_timestamp := pending_deleted_pages_info[page_id][1]),
            discuss,
        )
    elif (
        score <= -10
        and pending_deleted_pages_info[page_id][0] > -10
        and pending_deleted_pages_info[page_id][1] - announce_time > 86400
    ):  # 72h->24h
        logger.info(f'将文章{url}的删除宣告倒计时从72小时修改为24小时，当前分数为{score}')
        pending_deleted_pages_info[page_id][0] = score
        edit_post(
            pending_deleted_pages_info[page_id][2],
            pending_deleted_pages_info[page_id][3],
            normal_delete(score, record_timestamp := announce_time + 86400),
            discuss,
        )
    if announce_time >= record_timestamp:
        logger.info('倒计时到期，加入生成删除宣告列表')
        pending_delete_list.append(
            [
                url,
                pending_deleted_pages_info[page_id][0],
                "normal" if original else "translate",
            ]
        )  # 加入pending_delete_list
    elif pending_deleted_pages_info.get(page_id) is not None:
        logger.info('倒计时未到期，加入等待倒计时文章列表')
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
        logger.info('文章已处于-30分以下，加入生成删除宣告列表')
        pending_delete_list.append(
            [url, pending_deleted_pages_info[page_id][0], "minusThirty"]
        )

@retry(stop=stop_after_attempt(max_attempt_number=5), reraise=True, after=after_log(logger, log_level=logging.WARNING))
def add_deleted_category():
    driver.get(lowest_rated_link)
    for i in driver.find_element(
        By.XPATH, '//*[@id="page-content"]/div[3]/table/tbody'
    ).find_elements(By.TAG_NAME, "tr")[1:]:
        info = i.find_elements(By.TAG_NAME, "td")
        url = info[0].find_element(By.TAG_NAME, "a").get_attribute("href")
        score = int(info[1].find_element(By.TAG_NAME, "span").text)
        pending_delete_list.append([url, score, "deleted"])

@retry(stop=stop_after_attempt(max_attempt_number=5), reraise=True, after=after_log(logger, log_level=logging.WARNING))
def check_pending_deleted_pages_info():
    for i in list(
        pending_deleted_pages_info.keys()
    ):  # 删除pending_deleted_pages_info中的无效页面
        driver.get(pending_deleted_pages_info[i][4] + "/norender/true")
        try:
            driver.find_element(By.ID, "more-options-button")
            logger.debug(f'{i}检查通过')
        except NoSuchElementException:
            logger.debug(f'准备清除{i}的相关信息')
            del pending_deleted_pages_info[i]


@retry(stop=stop_after_attempt(max_attempt_number=5), reraise=True, after=after_log(logger, log_level=logging.WARNING))
def generate_announce(page):
    url, release_score, page_type  = page
    index = -1
    logger.info(f'正在生成{url}的删除宣告')
    for j, value in enumerate(js_result):
        if value["link"] == url:
            logger.debug('js_result已存在该页面')
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
        logger.info(f'当前页面类型为{js_result[index]["page_type"]}')


def main():
    global pending_delete_list, pending_delete_pages, deviant, js_result
    deviant = []  # 错误信息
    js_result = []  # 自删页面，低分翻译页面-30，以下页面，-30~+5页面相关信息
    pending_delete_list = []  # 待检验页面
    pending_delete_pages = []  # 在倒计时中的页面
    driver.get(lowest_rated_link)
    logger.info('开始为原创文章添加待删除标签')
    for page in get_page_list(1): # 为原创文章添加“待删除”
        add_original_pending_tag(page)
    driver.get(lowest_rated_link)  # 为翻译文章添加“待删除”
    logger.info('开始为翻译文章添加待删除标签')
    for url,_ in get_page_list(4):
        add_translate_pending_tag(url)
    driver.get(lowest_rated_link)
    logger.info('开始更新待删除文章信息')
    for page in get_page_list(2): # 整理待删除文章
        check_pending_pages(page)
    logger.info('将自删页面加入待删除列表')
    add_deleted_category()
    logger.info('删除待删除页面信息中的不存在页面')
    check_pending_deleted_pages_info()
    with open("deleted_pages.pkl", "wb") as file:
        pickle.dump(pending_deleted_pages_info, file)
    logger.debug(f'保存待删除页面信息：{pending_deleted_pages_info}')
    logger.info('开始检验并生成删除宣告')
    for page in pending_delete_list:  # 检验删除宣告
        generate_announce(page)
    logger.info('导出js文件')
    logger.debug(pending_delete_pages,js_result,deviant)
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
    logger.info('初始化完成')
    flag = 0
    while flag < 5:
        try:
            response = requests.get(lowest_rated_link)
            logger.debug('检验互联网链接情况')
            if response.status_code == 200:
                logger.info('开始启动页面管理程序')
                main()
                logger.info('主程序运行完成')
                time.sleep(1800)
                flag = 0
            else:
                logger.warning('网络错误，10s后重试')
                time.sleep(10)
        except Exception as e:
            flag += 1
            exc_type, exc_value, exc_traceback_obj = sys.exc_info()
            logger.error(f'第{flag}/5次重试，错误类型：{exc_type}，内容：{exc_value},3s后重试')
            traceback.print_exc()
            time.sleep(3)
    logger.critical('多次错误致使程序退出，等待人工重新启动')

driver.close()
