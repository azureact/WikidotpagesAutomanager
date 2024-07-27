from datetime import datetime
import json
import logging
import pickle
import re
import sys
import time
import traceback
from typing import Callable
from bs4 import BeautifulSoup
import wikidot
from wikidot.common import exceptions
from wikidot.util.parser import odate as odate_parser
from wikidot.util.parser import user as user_parser
import yaml
from httpx import ConnectError, ConnectTimeout


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler(
    f"logs/{datetime.now().strftime('%Y-%m-%d')}.txt")
console_handler.setLevel(logging.INFO)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addHandler(file_handler)


with open("deleted_pages.pkl", "rb") as file:
    pending_pages: dict[int, list] = pickle.load(file)
logger.info(f'载入历史数据：{pending_pages}')

with open("config.yaml", "r") as f:
    config: dict = yaml.safe_load(f)

deviant: list[dict] = []
staff_unix_names: list[str] = config["staffs"]
pending_delete_pages: list[dict] = []
pending_check_pages: list[dict] = []
js_result: list[dict] = []

def Retry(retry_text: str | None = None, last_text: str | None = None, times: int = 3, ifRaise: bool = False):
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            for i in range(times):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if retry_text is not None:
                        logger.warning(retry_text)
                    if i == times - 1:
                        if last_text is not None:
                            logger.error(last_text)
                        if ifRaise:
                            raise e
        return wrapper
    return decorator

wd = wikidot.Client(username=config["username"], password=config["password"])
site = wd.site.get(config["siteUnixName"])

@Retry(last_text="放弃重试，跳过修改")
def edit_post(thread_id: int, post_id: int, title: str | None = None, source: str | None = None):
    if title is None and source is None:
        logger.info("标题与源代码为空，放弃修改")
        return

    response = site.amc_request(
        [
            {
                "postId": post_id,
                "threadId": thread_id,
                "moduleName": "forum/sub/ForumEditPostFormModule"
            }
        ]
    )[0]
    html = BeautifulSoup(response.json()["body"], "lxml")
    current_id = int(html.select(
        "form#edit-post-form>input")[1].get("value"))
    current_title = html.select_one("input#np-title").get("value")
    current_source = html.select_one("textarea#np-text").get_text()

    if current_title == title and current_source == source:
        logger.info("标题与源代码和原帖相同，放弃修改")
        return
    if title is None:
        title = current_title
    if source is None:
        source = current_source

    response = site.amc_request(
        [
            {
                "postId": post_id,
                "currentRevisionId": current_id,
                "title": title,
                "source": source,
                "action": "ForumAction",
                "event": "saveEditPost",
                "moduleName": "Empty"
            }
        ]
    )[0]

    error_dict = {
        "threadId": thread_id,
        "postId": post_id,
        "title": title,
        "source": source,
        "errorType": "edit_post_unknown",
    }
    status = response.json()["status"]
    if status == "no_permission":
        error_dict["errorType"] = "edit_post_permission"
        deviant.append(error_dict)
        logger.warning("缺少编辑权限，跳过修改")
    elif status == "ok":
        if error_dict in deviant:
            deviant.remove(error_dict)
    else:
        logger.warning(f"编辑失败，状态为{status}，准备重试")
        if error_dict not in deviant:
            deviant.append(error_dict)
        raise exceptions.WikidotStatusCodeException(status_code=status)


@Retry(last_text="放弃重试，跳过创建")
def new_post(thread_id: int, title: str = "", source: str = "", parent_id: int = ""):
    if source == "":
        logger.info("源代码为空，放弃创建")
        return

    response = site.amc_request(
        [
            {
                "threadId": thread_id,
                "parentId": parent_id,
                "title": title,
                "source": source,
                "action": "ForumAction",
                "event": "savePost",
                "moduleName": "Empty"
            }
        ]
    )[0]

    error_dict = {
        "threadId": thread_id,
        "title": title,
        "source": source,
        "errorType": "new_post_unknown",
    }
    status = response.json()["status"]
    if status == "no_permission":
        error_dict["errorType"] = "new_post_permission"
        deviant.append(error_dict)
        logger.warning("缺少编辑权限，跳过创建")
    elif status == "ok":
        if error_dict in deviant:
            deviant.remove(error_dict)
    else:
        logger.warning(f"编辑失败，状态为{status}，准备重试")
        if error_dict not in deviant:
            deviant.append(error_dict)
        raise exceptions.WikidotStatusCodeException(status_code=status)

@Retry(last_text="放弃重试，跳过修改")
def edit_tags(page_id: int, tags: str):
    response = site.amc_request(
        [
            {
                "tags": tags,
                "pageId": page_id,
                "action": "WikiPageAction",
                "event": "saveTags",
                "moduleName": "Empty"
            }
        ]
    )[0]

    error_dict = {
        "pageId": page_id,
        "tags": tags,
        "errorType": "edit_tags_unknown",
    }
    status = response.json()["status"]
    if status == "no_permission":
        error_dict["errorType"] = "edit_tags_permission"
        deviant.append(error_dict)
        logger.warning("缺少编辑权限，跳过创建")
    elif status == "ok":
        if error_dict in deviant:
            deviant.remove(error_dict)
    else:
        logger.warning(f"编辑失败，状态为{status}，准备重试")
        if error_dict not in deviant:
            deviant.append(error_dict)
        raise exceptions.WikidotStatusCodeException(status_code=status)

def translate_delete(timer: float) -> str:  # 简写翻译删除文字
    return f"""
        由于翻译质量不佳，宣告删除。
        [[iframe https://timer.backroomswiki.cn/timer/time={timer*1000}/type=delete style="width: 400px; height: 65px;"]]"""

def normal_delete(score: int, timer: float) -> str:  # 简写正常删除文字
    return f"""
    由于条目的分数为{score}分，{"且距离发布时间已满1个月，" if score > -2 else ""}现根据[[[deletions-policy|删除政策]]]，宣告将删除此页：
    [[iframe https://timer.backroomswiki.cn/timer/time={timer*1000}/type=delete style="width: 400px; height: 65px;"]]
    如果你不是作者又想要重写该条目，请在此帖回复申请。请先取得作者的同意，并将原文的源代码复制至沙盒里。除非你是工作人员，否则请勿就申请重写以外的范围回复此帖。"""


def get_posts(thread_id: int) -> list[dict]:
    response = site.amc_request(
        [
            {
                "t": thread_id,
                "moduleName": "forum/ForumViewThreadModule"
            }
        ]
    )[0]
    
    html = BeautifulSoup(response.json()["body"], "lxml")
    if (pagerno := html.select_one("span.pager-no")) is None:
        pagers = 1
    else:
        pagers = int(re.search(r"of (\d+)", pagerno.text).group(1))

    responses = site.amc_request(
        [
            {
                "pageNo": no + 1,
                "t": thread_id,
                "order": "",
                "moduleName": "forum/ForumViewThreadPostsModule",
            }
            for no in range(pagers)
            ]
        )

    posts = []

    for response in responses:
        html = BeautifulSoup(response.json()["body"], "lxml")
        for post in html.select("div.post"):
            cuser = post.select_one("div.info span.printuser")
            codate = post.select_one("div.info span.odate")
            if (parent := post.parent.get("id")) != "thread-container-posts":
                parent_id = int(re.search(r"fpc-(\d+)", parent).group(1))
            else:
                parent_id = ""

            posts.append({
                "id" : int(re.search(r"post-(\d+)", post.get("id")).group(1)),
                "thread_id" : thread_id,
                "title" : post.select_one("div.title").text.strip(),
                "parent_id" : parent_id,
                "created_by" : user_parser(wd, cuser),
                "created_at" : odate_parser(codate),
                "source_ele" : post.select_one("div.content")
            })

    return posts

@Retry(ifRaise=True)
def get_discuss_id(page_id: int) -> int:
    response = site.amc_request(
        [
            {
                "page_id": page_id,
                "action": "ForumAction",
                "event": "createPageDiscussionThread",
                "moduleName": "Empty"
            }
        ]
    )[0]

    return int(response.json()["thread_id"])

def find_staff_post(posts: list[dict]) -> dict:
    for post in posts:
        title = post["title"]
        user = post["created_by"].name
        if "职员帖" in title and "删除宣告" in title and user in staff_unix_names:
            return post

@Retry(ifRaise=True)
def check_original_pages():
    pages = site.pages.search(
        category="-reserve",
        tags="-归档 -管理 -作者 -待删除 -重写中 -功能 -_低分删除豁免 原创 _test -组件后端 -组件 -总览",
        rating="<5"
    )

    for page in pages:
        current_time = time.time()
        created_time = page.created_at.timestamp()

        if pending_pages.get(page.id) is not None:
            logger.info("移除pending_pages中的数据")
            del pending_pages[page.id]
        
        if current_time - created_time >= 2678400 and "补充材料" not in page.tags:
            expected_time = 259200
        elif page.rating <= -2:
            expected_time = 259200 if page.rating > -10 else 86400
        else:
            logger.info(f"页面分数为{page.rating}，不满足删除条件，跳过此页面")
            continue
        
        discuss_id = get_discuss_id(page.id)
        deletion_post = find_staff_post(get_posts(discuss_id))
        post_source = normal_delete(page.rating, current_time + expected_time)
        if deletion_post is None:
            new_post(discuss_id,
                     "职员帖：删除宣告",
                     post_source
                     )
        else:
            edit_post(discuss_id,
                      deletion_post["id"],
                      source=post_source
                      )

        for error in deviant:
            if error.get("threadId") == discuss_id and error.get("source") == post_source:
                continue
        edit_tags(page.id, " ".join(page.tags) + " 待删除")

@Retry(ifRaise=True)
def check_translate_pages():
    pages = site.pages.search(
        category="-rate -fragment -reserve",
        tags="-_低分删除豁免 -已归档 -功能 -管理 -作者 -待删除 -总览 -组件 -旧页面  -组件后端 -重定向 -重写中 -原创 -掩藏页 -职员记号", 
        rating="<0"
    )

    for page in pages:
        current_time = time.time()
        created_time = page.created_at.timestamp()

        if current_time - created_time < 86400:
            logger.info("不满足删除条件，跳过此页面")
            continue
        
        for target_site_name in config["sites"]:
            target_site = wd.site.get(target_site_name)
            if target_site.page.get(page.name, False) is not None:
                break
        else:
            edit_tags(page.id, " ".join(page.tags) + " 原创")
            logger.info("判断为原创页面，补充原创标签")
            continue
        
        if pending_pages.get(page.id) is not None:
            logger.info("移除pending_pages中的数据")
            del pending_pages[page.id]

        discuss_id = get_discuss_id(page.id)
        deletion_post = find_staff_post(get_posts(discuss_id))
        post_source = translate_delete(current_time + 86400)
        if deletion_post is None:
            new_post(discuss_id,
                     "职员帖：删除宣告",
                     post_source
                     )
        else:
            edit_post(discuss_id,
                      deletion_post["id"],
                      source=post_source
                      )

        for error in deviant:
            if error.get("threadId") == discuss_id and error.get("source") == post_source:
                continue
        edit_tags(page.id, " ".join(page.tags) + " 待删除")

@Retry(ifRaise=True)
def check_pending_pages():
    pages = site.pages.search(
        category="-reserve",
        tags="-已归档 -管理 +待删除 -重写中 -_低分删除豁免 -职员记号"
    )

    for page in pages:
        current_time = time.time()
        created_time = page.created_at.timestamp()
        discuss_id = get_discuss_id(page.id)
        deletion_post = find_staff_post(get_posts(discuss_id))
        tags = page.tags
        original = "原创" in tags

        if deletion_post is not None:
            source = deletion_post["source_ele"]
            if "分数回升" in source.text:
                edit_tags(page.id, " ".join(page.tags).replace("待删除", ""))
                logger.info("检测到删除宣告内容为分数回升，跳过页面")
                continue
            
            timer_link = source.select_one("iframe").get("src")
            if "arandintday.github.io" in timer_link:
                record_timestamp = float(
                    re.search(r"timestamp=(\d+)", timer_link).group(1)) / 1000
            elif "timer.backroomswiki.cn" in timer_link:
                if ".000Z" in timer_link:
                    record_timestamp = datetime.fromisoformat(
                        re.search(r"/time=(.*?)\.000Z", timer_link).group(1)).timestamp()
                else:
                    record_timestamp = float(
                        re.search(r"/time=(\d+)", timer_link).group(1)) / 1000
            else:
                logger.warning("未找到时间戳")
                continue
            logger.info(f"删除宣告时间戳为{record_timestamp}")

            if "翻译" in source.text:
                logger.debug('检测到删除宣告为翻译文章')
                if original:
                    logger.info('文章为原创文章但使用翻译文章的删除宣告，准备重置删除宣告')
                    record_timestamp = current_time + 259200
                    edit_post(discuss_id, deletion_post["id"], source=normal_delete(
                        page.rating, record_timestamp))
                    page_score = -2 if page.rating < -10 else page.rating
                else:
                    page_score = page.rating if page.id not in pending_pages else pending_pages[page.id][0]
            else:
                matches = re.search(r"分数为 ?(-?\d+) ?分", source.text)
                if matches is None:
                    logger.warning("未找到分数")
                    continue
                else:
                    page_score = int(matches.group(1))
            if page_score <= -10 and record_timestamp < current_time + 259200:
                basic_timestamp = record_timestamp if page.id not in pending_pages else pending_pages[page.id][1]
            else:
                basic_timestamp = record_timestamp
            pending_pages[page.id] = [
                page_score,
                basic_timestamp,
                page.fullname
            ]
            logger.info(f'{page.get_url()}的页面信息保存完成')
        else:
            edit_tags(page.id, " ".join(page.tags).replace("待删除", ""))
            logger.warning("未找到删除帖")
            continue

        if (
            page.rating > -2 and current_time - created_time < 2678400 and original
            or page.rating >= 5
            or not original and page.rating >= 0
        ):
            edit_post(
                discuss_id,
                deletion_post["id"],
                source="【分数回升，倒计时停止】"
            )
            del pending_pages[page.id]
            edit_tags(page.id, " ".join(page.tags).replace("待删除", ""))
            logger.info('文章分数回升，取消删除并删除页面信息')
        elif pending_pages[page.id][0] <= -10 and page.rating > -10 and original:
            logger.info(f'将文章{page.get_url()}的删除宣告倒计时从24小时修改为72小时，当前分数为{page.rating}')
            pending_pages[page.id][0] = page.rating
            edit_post(
                discuss_id,
                deletion_post["id"],
                source=normal_delete(page.rating, record_timestamp := pending_pages[page.id][1])
            )
        elif (page.rating <= -10 
              and pending_pages[page.id][0] > -10 
              and pending_pages[page.id][1] - current_time > 86400 
              and original):
            logger.info(f'将文章{page.get_url()}的删除宣告倒计时从72小时修改为24小时，当前分数为{page.rating}')
            pending_pages[page.id][0] = page.rating
            edit_post(
                discuss_id,
                deletion_post["id"],
                source=normal_delete(page.rating, record_timestamp := current_time + 86400))
        if current_time >= record_timestamp:
            logger.info('倒计时到期，加入生成删除宣告列表')
            pending_check_pages.append(
                [
                    page.fullname,
                    pending_pages[page.id][0],
                    "normal" if original else "translate",
                ]
            )
        elif page.id in pending_pages:
            logger.info('倒计时未到期，加入等待倒计时文章列表')
            pending_delete_pages.append(
                {
                    "link": page.get_url(),
                    "title": page.title,
                    "score": page.rating,
                    "release_score": page_score,
                    "time": 72 if page_score > -10 else 24,
                    "discuss_link": f"https://{config["siteUnixName"]}.wikidot.com/t-{discuss_id}",
                    "post_id": deletion_post["id"],
                    "isOriginal": original,
                    "timestamp": record_timestamp,
                }
            )
        if page.rating <= -30:
            logger.info('文章已处于-30分以下，加入生成删除宣告列表')
            pending_check_pages.append(
                [page.fullname, pending_pages[page.id][0], "minusThirty"]
            )

@Retry(ifRaise=True)
def check_deleted_pages():
    pages = site.pages.search(
        category="deleted",
        tags="-已归档 -重写中 -职员记号"
    )

    for page in pages:
        pending_check_pages.append([page.fullname, page.rating, "deleted"])

@Retry(ifRaise=True)
def check_pending_delete_pages():
    for page_id in list(pending_pages.keys()):
        if site.page.get(pending_pages[page_id][2], False) is None:
            del pending_pages[page_id]

@Retry(ifRaise=True)
def generate_announce():
    for page_info in pending_check_pages:
        index = -1
        unix_name, release_score, page_type = page_info
        logger.info(f'正在生成{unix_name}的删除宣告')
        for j, value in enumerate(js_result):
            if value["link"] == unix_name:
                index = j
                break
        if index == -1:
            page = site.page.get(unix_name)
            js_result.append(
                {
                    "link": page.get_url(),
                    "title": page.title,
                    "score": page.rating,
                    "time": (
                        24 if release_score <= -10 or page_type == "translate" else 72
                    ),
                    "context": page.source.wiki_text,
                    "page_type": [page_type],
                }
            )
        else:
            if page_type == "normal":
                js_result[index]["release_score"] = release_score
            js_result[index]["page_type"] += [page_type]
            logger.info(f'当前页面类型为{js_result[index]["page_type"]}')

def main():
    global deviant, js_result, pending_check_pages, pending_delete_pages
    deviant = [] # 错误信息
    js_result = []  # 自删页面，低分翻译页面-30，以下页面，-30~+5页面相关信息
    pending_check_pages = [] # 待生成页面
    pending_delete_pages = [] # 在倒计时中的页面
    logger.info('开始为原创文章添加待删除标签')
    check_original_pages()
    logger.info('开始为翻译文章添加待删除标签')
    check_translate_pages()
    logger.info('开始更新待删除文章信息')
    check_pending_pages()
    logger.info('将自删页面加入待删除列表')
    check_deleted_pages()
    logger.info('删除待删除页面信息中的不存在页面')
    check_pending_delete_pages()
    with open("deleted_pages.pkl", "wb") as file:
        pickle.dump(pending_pages, file)
        logger.debug(f'保存待删除页面信息：{pending_pages}')
    logger.info('开始检验并生成删除宣告')
    generate_announce()
    logger.info('导出js文件')
    logger.debug(pending_delete_pages, js_result, deviant)
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
    flag = 0
    while flag < 5:
        try:
            logger.info('开始启动页面管理程序')
            main()
            logger.info('主程序运行完成')
            time.sleep(1800)
            flag = 0
        except (ConnectError, ConnectTimeout):
            logger.error("网络错误，1分钟后重试")
            time.sleep(60)
        except Exception as e:
            flag += 1
            exc_type, exc_value, exc_traceback_obj = sys.exc_info()
            logger.error(f'第{flag}/5次重试，错误类型：{exc_type}，内容：{exc_value},3s后重试')
            traceback.print_exc()
            time.sleep(3)
    logger.critical('多次错误致使程序退出，等待人工重新启动')
