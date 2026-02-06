import asyncio
import aiohttp
import random
import json
import logging
import time
import sys
import re
import os
from typing import Optional, Dict, Union
from dataclasses import dataclass
from aiohttp import ClientSession

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler("sender.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

@dataclass
class SenderConfig:
    target_id: str  # BV号或直播间ID
    cookies_file: str = "cookies.json"
    interval_min: float = 0.5
    interval_max: float = 1.0
    mode: str = "auto"  # "live" or "video" or "auto"
    max_count: int = 0  # 0 为无限
    run_duration: int = 0  # 0 为无限，单位秒

class BilibiliDanmakuSender:
    def __init__(self, config: SenderConfig, shared_cookies: Optional[Dict[str, str]] = None):
        self.config = config
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Origin': 'https://www.bilibili.com'
        }
        self.cookies: Dict[str, str] = shared_cookies or {}
        # 如果传入了共享Cookie，则直接解析 CSRF
        if shared_cookies:
             self.csrf_token = self.cookies.get('bili_jct')
             self.uid = self.cookies.get('DedeUserID')

        self.real_room_id: Optional[int] = None
        self.video_oid: Optional[int] = None
        
        # 统计数据
        self.stats = {
            'total': 0,
            'success': 0,
            'fail': 0,
            'start_time': time.time()
        }
        
        # 弹幕池
        self.msgs = [
            "赴汤蹈火鸡面#71395",
            "赴汤蹈火鸡面#71395赴汤蹈火鸡面#71395"
        ]
        
    def load_cookies(self) -> bool:
        """从文件加载Cookies"""
        # 如果已经加载（通过共享注入），则直接返回 True
        if self.cookies and self.csrf_token:
             return True

        try:
            if not os.path.exists(self.config.cookies_file):
                logging.error(f"Cookies文件不存在: {self.config.cookies_file}")
                return False

            with open(self.config.cookies_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # 支持 JSON 或 Netscape 格式，这里简化假定是 JSON 或 key=value 字符串
                try:
                    self.cookies = json.loads(content)
                except json.JSONDecodeError:
                    # 尝试解析 key=value; key=value 格式
                    self.cookies = {k.strip(): v.strip() for k, v in [i.split('=', 1) for i in content.split(';') if '=' in i]}
            
            # 获取CSRF Token (bili_jct)
            self.csrf_token = self.cookies.get('bili_jct')
            self.uid = self.cookies.get('DedeUserID')
            
            if not self.csrf_token:
                logging.error("无法从Cookies中找到 'bili_jct' (CSRF Token)")
                return False
            
            logging.info(f"Cookies加载成功，用户ID: {self.uid}")
            return True
        except Exception as e:
            logging.error(f"加载Cookies失败: {e}")
            return False

    async def get_target_info(self, session: ClientSession) -> bool:
        """获取目标信息（直播间真实ID或视频OID）"""
        target = self.config.target_id
        
        # 自动推断模式
        if self.config.mode == "auto":
            if target.upper().startswith("BV"):
                self.config.mode = "video"
            else:
                self.config.mode = "live"
        
        logging.info(f"当前模式: {self.config.mode}, 目标: {target}")

        try:
            if self.config.mode == "live":
                # 获取真实房间号
                url = f'https://api.live.bilibili.com/room/v1/Room/room_init?id={target}'
                async with session.get(url, headers=self.headers) as resp:
                    data = await resp.json()
                    if data['code'] == 0:
                        self.real_room_id = data['data']['room_id']
                        status = "直播中" if data['data']['live_status'] == 1 else "未开播"
                        logging.info(f"获取直播间信息成功: 真实ID={self.real_room_id}, 状态={status}")
                        return True
                    else:
                        logging.error(f"获取直播间信息失败: {data['msg']}")
                        return False
            
            elif self.config.mode == "video":
                # 获取视频CID (OID)
                url = f'https://api.bilibili.com/x/web-interface/view?bvid={target}'
                async with session.get(url, headers=self.headers) as resp:
                    data = await resp.json()
                    if data['code'] == 0:
                        self.video_oid = data['data']['cid']
                        logging.info(f"获取视频信息成功: OID(CID)={self.video_oid}, 标题={data['data']['title']}")
                        return True
                    else:
                        logging.error(f"获取视频信息失败: {data['message']}")
                        return False
            return False
        except Exception as e:
            logging.error(f"初始化目标信息异常: {e}")
            return False

    async def send_live_danmaku(self, session: ClientSession, msg: str) -> bool:
        """发送直播弹幕"""
        url = 'https://api.live.bilibili.com/msg/send'
        data = {
            'bubble': '0',
            'msg': msg,
            'color': '16777215',
            'mode': '1',
            'fontsize': '25',
            'rnd': str(int(time.time())),
            'roomid': str(self.real_room_id),
            'csrf': self.csrf_token,
            'csrf_token': self.csrf_token
        }
        
        try:
            async with session.post(url, data=data, headers=self.headers, cookies=self.cookies) as resp:
                result = await resp.json()
                if result['code'] == 0:
                    logging.info(f"✅ [成功] 发送内容: {msg[:10]}...")
                    return True
                else:
                    logging.warning(f"❌ [失败] 错误码: {result['code']}, 信息: {result['msg']}")
                    # 如果被封禁，暂停较长时间
                    if result['code'] == 1003 or "封" in str(result.get('msg', '')):
                        logging.critical("检测到可能的封禁/禁言，暂停 60 秒...")
                        await asyncio.sleep(60)
                    return False
        except Exception as e:
            logging.error(f"请求异常: {e}")
            return False

    async def send_video_danmaku(self, session: ClientSession, msg: str) -> bool:
        """发送视频弹幕"""
        url = 'https://api.bilibili.com/x/v2/dm/post'
        data = {
            'type': '1',
            'oid': str(self.video_oid),
            'msg': msg,
            'aid': str(self.video_oid), # 这里的aid其实通常不是必须的，主要是oid
            'progress': str(random.randint(1000, 5000)), # 随机视频位置 1-5秒
            'color': '16777215',
            'fontsize': '25',
            'pool': '0',
            'mode': '1', # 滚动弹幕
            'rnd': str(int(time.time())),
            'plat': '1',
            'csrf': self.csrf_token
        }
        
        try:
            async with session.post(url, data=data, headers=self.headers, cookies=self.cookies) as resp:
                # 视频弹幕API返回是XML或特殊的JSON，视Accept而定，标准API返回json
                # 注意：发送视频弹幕成功通常返回 code 0
                result = await resp.json()
                if result['code'] == 0:
                    logging.info(f"✅ [成功] 视频弹幕发送: {msg[:10]}...")
                    return True
                else:
                    logging.warning(f"❌ [失败] 错误码: {result['code']}, 信息: {result['message']}")
                    if result['code'] == 36703: # 频率限制
                        await asyncio.sleep(5)
                    return False
        except Exception as e:
            # 有时候返回不是JSON，可能是xml
            logging.error(f"请求异常(可能非JSON响应): {e}")
            return False

    async def run(self, session: Optional[ClientSession] = None):
        logging.info(f"[{self.config.target_id}] 🚀 给定目标 任务启动...")
        
        if not self.load_cookies():
            logging.error(f"[{self.config.target_id}] 无法加载配置，任务退出")
            return

        # 如果没有传入外部Session，则自己创建一个（用于兼容）
        local_session = None
        if session is None:
            local_session = aiohttp.ClientSession()
            active_session = local_session
        else:
            active_session = session

        try:
            # 初始化目标
            if not await self.get_target_info(active_session):
                return
            
            logging.info(f"[{self.config.target_id}] ✨ 开始循环发送弹幕...")
            
            msg_index = 0
            
            while True:
                # 检查退出条件
                if self.config.max_count > 0 and self.config.stats['success'] >= self.config.max_count:
                    logging.info(f"[{self.config.target_id}] 已达到设定发送次数")
                    break
                
                if self.config.run_duration > 0 and (time.time() - self.config.stats['start_time']) > self.config.run_duration:
                    logging.info(f"[{self.config.target_id}] 已达到设定运行时间")
                    break

                # 准备发送
                current_msg = self.msgs[msg_index % len(self.msgs)]
                msg_index += 1
                
                # 发送动作
                success = False
                if self.config.mode == "live":
                    success = await self.send_live_danmaku(active_session, current_msg)
                else:
                    success = await self.send_video_danmaku(active_session, current_msg)
                
                # 统计
                self.stats['total'] += 1
                if success:
                    self.stats['success'] += 1
                else:
                    self.stats['fail'] += 1

                # 随机等待
                delay = random.uniform(self.config.interval_min, self.config.interval_max)
                # 微小的抖动
                delay += random.uniform(-0.1, 0.1)
                if delay < 0.2: delay = 0.2
                
                await asyncio.sleep(delay)

            # 最终报告
            logging.info("-" * 30)
            logging.info(f"[{self.config.target_id}] 运行结束。总尝试: {self.stats['total']}, 成功: {self.stats['success']}, 失败: {self.stats['fail']}")
            logging.info("-" * 30)
        finally:
            if local_session:
                await local_session.close()

async def main():
    # --- 用户配置区域 ---
    raw_input = input("请输入直播间ID或视频BV号 (多个用空格或逗号分隔): ").strip()
    
    # 支持逗号、分号、空格分隔
    targets = [t.strip() for t in re.split(r'[,;，；\s]+', raw_input) if t.strip()]
    
    if not targets:
        print("未输入有效目标")
        return

    # 获取脚本所在目录，确保能找到同级目录下的cookies.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cookies_path = os.path.join(script_dir, "cookies.json")

    # 预加载 Cookies，只读取一次文件
    shared_cookies = {}
    if os.path.exists(cookies_path):
        try:
            with open(cookies_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                try:
                    shared_cookies = json.loads(content)
                except json.JSONDecodeError:
                    shared_cookies = {k.strip(): v.strip() for k, v in [i.split('=', 1) for i in content.split(';') if '=' in i]}
            logging.info("Cookies 预加载成功")
        except Exception as e:
            logging.error(f"预加载 Cookies 失败: {e}")
    else:
        logging.error(f"配置文件未找到: {cookies_path}")
        return

    # 创建所有任务
    tasks = []
    
    # 共享Session
    async with aiohttp.ClientSession() as session:
        for target in targets:
            config = SenderConfig(
                target_id=target,
                cookies_file=cookies_path,
                interval_min=0.8,
                interval_max=1.5,
                mode="auto"
            )
            sender = BilibiliDanmakuSender(config, shared_cookies=shared_cookies)
            # 添加到任务列表
            tasks.append(sender.run(session))
        
        if not tasks:
            return

        print(f"即将对 {len(tasks)} 个目标 {targets} 启动任务...")
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户手动停止")
