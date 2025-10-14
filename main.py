# -*- coding: utf-8 -*-
import os
import sys
import threading
import re
import time
from datetime import datetime
from urllib.parse import urlparse

# Windows 编码设置
if sys.platform == 'win32':
    try:
        import codecs

        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except:
        pass

# 设置环境变量（在导入 Kivy 之前）
os.environ['KIVY_TEXT'] = 'pil'

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.core.window import Window
from kivy.clock import Clock, mainthread
from kivy.utils import platform
from kivy.metrics import dp
from kivy.utils import platform

if platform == 'android':
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.INTERNET,
        Permission.WRITE_EXTERNAL_STORAGE,
        Permission.READ_EXTERNAL_STORAGE
    ])

# 尝试导入 requests
try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class FontManager:
    """字体管理器，解决中文显示问题"""

    def __init__(self):
        self.chinese_font = self.detect_chinese_font()

    def detect_chinese_font(self):
        """检测可用的中文字体"""
        if sys.platform == 'win32':
            fonts = ['Microsoft YaHei', 'SimHei', 'SimSun', 'KaiTi']
            return fonts[1]
        elif sys.platform == 'darwin':
            return 'PingFang SC'
        else:
            return 'Droid Sans Fallback'

    def apply_font(self, widget, font_size='14sp'):
        """为控件应用字体"""
        try:
            if hasattr(widget, 'font_name'):
                widget.font_name = self.chinese_font
            if hasattr(widget, 'font_size'):
                widget.font_size = font_size
        except Exception as e:
            print(f"应用字体失败: {e}")


# 创建全局字体管理器
font_manager = FontManager()


class LongPressTextInput(TextInput):
    """支持长按的文本输入框"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.long_press_time = 0.5  # 长按时间阈值（秒）
        self.long_press_event = None
        self.is_long_press = False

    def on_touch_down(self, touch):
        """触摸按下事件"""
        if self.collide_point(*touch.pos):
            # 开始计时长按
            self.is_long_press = False
            self.long_press_event = Clock.schedule_once(self._on_long_press, self.long_press_time)

        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        """触摸抬起事件"""
        if self.collide_point(*touch.pos) and self.long_press_event:
            # 取消长按计时器
            self.long_press_event.cancel()
            self.long_press_event = None

            # 如果不是长按，则执行普通点击操作
            if not self.is_long_press:
                self._on_short_press()

        return super().on_touch_up(touch)

    def _on_long_press(self, dt):
        """长按事件处理"""
        self.is_long_press = True
        if hasattr(self, 'on_long_press'):
            self.on_long_press()

    def _on_short_press(self):
        """短按事件处理"""
        if hasattr(self, 'on_short_press'):
            self.on_short_press()


class AutoScrollLabel(ScrollView):
    """自动滚动到底部的 ScrollView"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.do_scroll_x = False  # 禁用水平滚动
        self.bar_width = dp(10)  # 滚动条宽度

        # 创建标签
        self.label = Label(
            size_hint_y=None,
            halign='left',
            valign='top'
        )
        self.label.bind(texture_size=self._update_label_height)
        self.add_widget(self.label)

        # 绑定宽度变化
        self.bind(width=self._update_text_size)

    def _update_text_size(self, instance, value):
        """更新文本尺寸以适应宽度"""
        # 设置文本宽度为 ScrollView 宽度减去滚动条宽度
        self.label.text_size = (self.width - self.bar_width - dp(10), None)

    def _update_label_height(self, instance, value):
        """更新标签高度以适应内容"""
        instance.height = max(instance.texture_size[1], self.height)
        # 自动滚动到底部
        self.scroll_y = 0

    def add_text(self, text):
        """添加文本并自动滚动到底部"""
        current_text = self.label.text
        if current_text:
            new_text = f"{current_text}\n{text}"
        else:
            new_text = text

        # 限制行数，避免内存问题
        lines = new_text.split('\n')
        if len(lines) > 50:  # 保留最后50行
            new_text = '\n'.join(lines[-50:])

        self.label.text = new_text
        # 确保滚动到底部
        Clock.schedule_once(self._scroll_to_bottom, 0.1)

    def _scroll_to_bottom(self, dt):
        """滚动到底部"""
        if self.vbar:
            self.scroll_y = 0

    def clear_text(self):
        """清空文本"""
        self.label.text = ""


class VideoDownloaderApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.downloading = False
        self.current_url = ""
        self.download_thread = None
        self.download_path = ""
        self.session = None
        self.start_time = 0

        # 设置下载路径
        if platform == 'android':
            try:
                from android.storage import primary_external_storage_path
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
                storage_path = primary_external_storage_path()
                self.download_path = os.path.join(storage_path, 'Download', 'VideoDownloader')
            except:
                self.download_path = os.path.join(os.path.expanduser('~'), 'Downloads', 'VideoDownloader')
        else:
            self.download_path = os.path.join(os.path.expanduser('~'), 'Downloads', 'VideoDownloader')

        # 确保下载目录存在
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

        # 创建 requests session
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })

    def build(self):
        # 设置窗口大小和颜色
        if sys.platform == 'win32':
            Window.size = (800, 700)
        else:
            Window.size = (400, 600)

        Window.clearcolor = (0.95, 0.95, 0.95, 1)

        # 主布局
        main_layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))

        # 标题
        title = Label(
            text='视频下载器',
            font_size='24sp',
            bold=True,
            size_hint_y=None,
            height=dp(50),
            color=(0.2, 0.2, 0.2, 1)
        )
        font_manager.apply_font(title, '24sp')
        main_layout.add_widget(title)

        # 检查依赖状态
        if not REQUESTS_AVAILABLE:
            warning_label = Label(
                text='警告: requests 库未安装，下载功能将不可用',
                size_hint_y=None,
                height=dp(30),
                color=(0.8, 0.2, 0.2, 1),
                font_size='12sp'
            )
            font_manager.apply_font(warning_label, '12sp')
            main_layout.add_widget(warning_label)
        else:
            info_label = Label(
                text='注意: 此版本仅支持抖音视频链接',
                size_hint_y=None,
                height=dp(30),
                color=(0.2, 0.5, 0.8, 1),
                font_size='12sp'
            )
            font_manager.apply_font(info_label, '12sp')
            main_layout.add_widget(info_label)

        # URL 输入区域
        url_section = BoxLayout(orientation='vertical', spacing=dp(10))

        url_label = Label(
            text='长按输入框可粘贴剪贴板内容',
            size_hint_y=None,
            height=dp(25),
            color=(0.3, 0.3, 0.3, 1)
        )
        font_manager.apply_font(url_label)
        url_section.add_widget(url_label)

        # URL 输入框和清空按钮的布局
        input_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(45), spacing=dp(10))

        # 使用支持长按的文本输入框
        self.url_input = LongPressTextInput(
            hint_text='长按此处可粘贴剪贴板内容，或输入包含链接的文本...',
            multiline=False,
            background_color=(1, 1, 1, 1),
            foreground_color=(0.2, 0.2, 0.2, 1),
            padding=dp(10),
            font_size='16sp',
            size_hint_x=0.7
        )
        font_manager.apply_font(self.url_input, '16sp')

        # 绑定长按和短按事件
        self.url_input.on_long_press = self.show_paste_options
        self.url_input.on_short_press = self.focus_input

        clear_btn = Button(
            text='清空',
            size_hint_x=0.3,
            background_color=(0.8, 0.5, 0.2, 1),
            color=(1, 1, 1, 1),
            font_size='14sp'
        )
        font_manager.apply_font(clear_btn, '14sp')
        clear_btn.bind(on_press=self.clear_input)

        input_layout.add_widget(self.url_input)
        input_layout.add_widget(clear_btn)
        url_section.add_widget(input_layout)

        main_layout.add_widget(url_section)

        # 下载按钮
        self.download_btn = Button(
            text='开始下载',
            size_hint_y=None,
            height=dp(55),
            background_color=(0.2, 0.7, 0.3, 1),
            color=(1, 1, 1, 1),
            font_size='18sp',
            bold=True
        )
        font_manager.apply_font(self.download_btn, '18sp')
        self.download_btn.bind(on_press=self.start_download)
        main_layout.add_widget(self.download_btn)

        # 进度条
        self.progress_bar = ProgressBar(
            max=100,
            value=0,
            size_hint_y=None,
            height=dp(10)
        )
        main_layout.add_widget(self.progress_bar)

        # 进度标签
        self.progress_label = Label(
            text='',
            size_hint_y=None,
            height=dp(25),
            color=(0.4, 0.4, 0.4, 1),
            font_size='12sp'
        )
        font_manager.apply_font(self.progress_label, '12sp')
        main_layout.add_widget(self.progress_label)

        # 状态显示区域
        status_section = BoxLayout(orientation='vertical', spacing=dp(10))

        status_label = Label(
            text='下载状态:',
            size_hint_y=None,
            height=dp(25),
            color=(0.3, 0.3, 0.3, 1)
        )
        font_manager.apply_font(status_label)
        status_section.add_widget(status_label)

        # 使用自动滚动的状态显示框
        self.status_scroll = AutoScrollLabel(
            size_hint_y=1
        )
        # 设置状态标签的样式
        status_label_style = self.status_scroll.label
        font_manager.apply_font(status_label_style, '14sp')
        status_label_style.color = (0.4, 0.4, 0.4, 1)
        status_label_style.halign = 'left'
        status_label_style.valign = 'top'

        status_section.add_widget(self.status_scroll)
        main_layout.add_widget(status_section)

        # 功能按钮区域
        button_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(45), spacing=dp(10))

        clear_log_btn = Button(
            text='清空日志',
            background_color=(0.7, 0.3, 0.5, 1),
            color=(1, 1, 1, 1)
        )
        font_manager.apply_font(clear_log_btn)
        clear_log_btn.bind(on_press=self.clear_log)

        open_folder_btn = Button(
            text='打开文件夹',
            background_color=(0.5, 0.3, 0.7, 1),
            color=(1, 1, 1, 1)
        )
        font_manager.apply_font(open_folder_btn)
        open_folder_btn.bind(on_press=self.open_download_folder)

        button_layout.add_widget(clear_log_btn)
        button_layout.add_widget(open_folder_btn)
        main_layout.add_widget(button_layout)

        # 应用启动时检查剪贴板
        Clock.schedule_once(self.check_clipboard, 1)

        return main_layout

    def focus_input(self):
        """聚焦输入框"""
        self.url_input.focus = True

    def show_paste_options(self):
        """显示粘贴选项"""
        clipboard_content = self.get_clipboard_content()
        if clipboard_content:
            extracted_url = self.extract_url_from_text(clipboard_content)
            if extracted_url:
                self.show_paste_prompt(extracted_url)
            else:
                self.show_popup("提示", "剪贴板中没有找到有效的链接")
        else:
            self.show_popup("提示", "剪贴板为空")

    def check_clipboard(self, dt):
        """检查剪贴板中是否有 URL 内容"""
        try:
            clipboard_content = self.get_clipboard_content()
            if clipboard_content:
                extracted_url = self.extract_url_from_text(clipboard_content)
                if extracted_url:
                    self.show_paste_prompt(extracted_url)
        except Exception as e:
            self.log_status(f"剪贴板检查失败: {str(e)}")

    def get_clipboard_content(self):
        """获取剪贴板内容"""
        try:
            if platform == 'android':
                from jnius import autoclass
                Context = autoclass('android.content.Context')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                clipboard = PythonActivity.mActivity.getSystemService(Context.CLIPBOARD_SERVICE)
                clip_data = clipboard.getPrimaryClip()
                if clip_data and clip_data.getItemCount() > 0:
                    return str(clip_data.getItemAt(0).getText())
            else:
                from kivy.core.clipboard import Clipboard
                return Clipboard.paste()
            return ""
        except Exception as e:
            self.log_status(f"获取剪贴板失败: {str(e)}")
            return ""

    def is_valid_url(self, text):
        """从字符串中提取有效的 HTTP/HTTPS 链接"""
        if not text:
            return None

        # 更全面的 URL 正则表达式，匹配各种格式的 URL
        url_pattern = re.compile(
            r'http[s]?://'  # http:// or https://
            r'(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|'
            r'(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            re.IGNORECASE
        )

        # 查找所有匹配的 URL
        urls = re.findall(url_pattern, text)

        # 过滤出有效的 URL
        valid_urls = []
        for url in urls:
            try:
                # 验证 URL 格式
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    # 确保 URL 完整（没有截断）
                    if not url.endswith(('...', '…')):
                        valid_urls.append(url)
            except Exception:
                continue

        # 返回第一个有效的 URL，如果没有则返回 None
        return valid_urls[0] if valid_urls else None

    def extract_url_from_text(self, text):
        """从文本中提取 URL 的主要方法"""
        # 首先尝试直接匹配
        direct_url = self.is_valid_url(text)
        if direct_url:
            return direct_url

        # 如果直接匹配失败，尝试从文本中提取
        # 常见的 URL 分隔符
        separators = [' ', '\n', '\t', ',', ';', '，', '。', '！', '？']

        for sep in separators:
            parts = text.split(sep)
            for part in parts:
                url = self.is_valid_url(part.strip())
                if url:
                    return url

        return None

    def is_video_url(self, url):
        """检查是否是视频 URL"""
        video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v']
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()

        # 检查路径中是否包含视频扩展名
        for ext in video_extensions:
            if path.endswith(ext):
                return True

        # 检查 Content-Type 头（需要发送 HEAD 请求）
        try:
            response = self.session.head(url, timeout=10, allow_redirects=True)
            content_type = response.headers.get('Content-Type', '').lower()
            return 'video' in content_type or any(ext.replace('.', '') in content_type for ext in video_extensions)
        except:
            return False

    def show_paste_prompt(self, url):
        """显示粘贴提示弹窗"""
        content = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))

        message_label = Label(
            text='检测到剪贴板中有视频链接，是否粘贴？',
            text_size=(Window.width * 0.7, None),
            halign='center'
        )
        font_manager.apply_font(message_label)
        content.add_widget(message_label)

        button_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(45), spacing=dp(10))

        paste_btn = Button(
            text='粘贴',
            background_color=(0.3, 0.6, 0.3, 1),
            color=(1, 1, 1, 1)
        )
        font_manager.apply_font(paste_btn)

        cancel_btn = Button(
            text='取消',
            background_color=(0.8, 0.3, 0.3, 1),
            color=(1, 1, 1, 1)
        )
        font_manager.apply_font(cancel_btn)

        popup = Popup(
            title='粘贴提示',
            content=content,
            size_hint=(0.8, 0.4),
            auto_dismiss=False
        )

        paste_btn.bind(on_press=lambda x: self.confirm_paste(url, popup))
        cancel_btn.bind(on_press=popup.dismiss)

        button_layout.add_widget(paste_btn)
        button_layout.add_widget(cancel_btn)
        content.add_widget(button_layout)

        popup.open()

    def confirm_paste(self, url, popup):
        """确认粘贴 URL"""
        self.url_input.text = url
        popup.dismiss()
        self.log_status("已从剪贴板粘贴 URL")

    def clear_input(self, instance):
        """清空输入框"""
        self.url_input.text = ""

    def clear_log(self, instance):
        """清空日志"""
        self.status_scroll.clear_text()

    def open_download_folder(self, instance):
        """打开下载文件夹"""
        try:
            if platform == 'android':
                from jnius import autoclass
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')

                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(Uri.parse(f"file://{self.download_path}"), "resource/folder")

                current_activity = PythonActivity.mActivity
                current_activity.startActivity(intent)
            elif sys.platform == 'win32':
                os.startfile(self.download_path)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', self.download_path])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', self.download_path])

            self.log_status(f"已打开下载文件夹: {self.download_path}")
        except Exception as e:
            self.log_status(f"打开文件夹失败: {str(e)}")

    def start_download(self, instance):
        """开始下载视频"""

        def get_vid(url):
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "pragma": "no-cache",
                "priority": "u=0, i",
                "sec-ch-ua": "\"Not;A=Brand\";v=\"99\", \"Google Chrome\";v=\"139\", \"Chromium\";v=\"139\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Windows\"",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
            }
            cookies = {
                "store-region": "cn-gz",
                "store-region-src": "uid",
                "live_use_vvc": "%22false%22",
                "bd_ticket_guard_client_web_domain": "2",
                "hevc_supported": "true",
                "SelfTabRedDotControl": "%5B%5D",
                "my_rd": "2",
                "n_mh": "YzA052LtpaKIpb_FJ-5HjSZvLFK9tIOICQBkCf8w-iI",
                "SEARCH_RESULT_LIST_TYPE": "%22multi%22",
                "SearchMultiColumnLandingAbVer": "2",
                "enter_pc_once": "1",
                "__live_version__": "%221.1.3.3838%22",
                "passport_csrf_token": "ed1c48b3766bdfe841f3c447817b6167",
                "passport_csrf_token_default": "ed1c48b3766bdfe841f3c447817b6167",
                "passport_mfa_token": "CjX2vVDmpZDsJ9d3O8ZBMXKOe5G0bt5ScqcebO0jA0lJHkO5Nc64cPwbX2OeW7ixL2Y38HerRxpKCjwAAAAAAAAAAAAATzxSdo7jh83Ei8pGMx02aPGtNGKc0ntPNEIXE4J2er51MoZQnHIMkvw5KPA9GETU6VsQtOT2DRj2sdFsIAIiAQPH%2F807",
                "d_ticket": "30aab26e36fca8a0480a7e3a56ceea1c0dfe9",
                "login_time": "1752549334069",
                "_bd_ticket_crypt_cookie": "7e58e859398639431e875f71c52e3814",
                "__security_mc_1_s_sdk_sign_data_key_web_protect": "a60dd64a-40a9-b4f7",
                "__security_server_data_status": "1",
                "UIFID_TEMP": "1b474bc7e0db9591e645dd8feb8c65aae4845018effd0c2743039a380ee64740e21e440ba4139a45db47af1e832bfc16aeb2fec4787335b93c61fc6f51038aa9f0f9e2d0cf7a92959cc1d7c5108ba683",
                "UIFID": "1b474bc7e0db9591e645dd8feb8c65aae4845018effd0c2743039a380ee64740e21e440ba4139a45db47af1e832bfc16d7c5cc5954dee5e8845d220444dc8118336f933d5b916552e095e5695357d9bb8c2fa792b80c26d303b3d97d6928974f417e0a070f97803b76b50a84f7876d5a6161fdaff94e43bf9a976d78b6c6be984e11be851231faa10e91f0d78edd57260530e8d465c2b8100f44aef71d86c3f4",
                "__security_mc_1_s_sdk_crypt_sdk": "d10c810c-462c-9835",
                "__security_mc_1_s_sdk_cert_key": "bf2cd445-46a8-85e7",
                "odin_tt": "768704dfae4d63e1183b25e211539afd5ec6918d48c34663ea86f91240b162915a4799e713c10e246f24901e3f5ae1cddb324d6d7d42bac156526b6858940b7c4ad7d9056633921e6c7dd5726de07ccc",
                "volume_info": "%7B%22volume%22%3A0.89%2C%22isMute%22%3Atrue%2C%22isUserMute%22%3Afalse%7D",
                "bd_ticket_guard_client_data": "eyJiZC10aWNrZXQtZ3VhcmQtdmVyc2lvbiI6MiwiYmQtdGlja2V0LWd1YXJkLWl0ZXJhdGlvbi12ZXJzaW9uIjoxLCJiZC10aWNrZXQtZ3VhcmQtcmVlLXB1YmxpYy1rZXkiOiJCS2dOOWF6eTdaZUVvUWljVUNHL1FpWFFvb2JjekNTNEpFSVdnVmR0REVhZitzME41TjB5YUp1M1kwRHk2RFd4ZjFrVktucEdybWFLQms3RXlQd0gxTkU9IiwiYmQtdGlja2V0LWd1YXJkLXdlYi12ZXJzaW9uIjoyfQ%3D%3D",
                "ttwid": "1%7CrmgdruTgXvGNo_74O4vCyVU_-Izlx2qjGgHoxFApmbU%7C1756531125%7C8f35700f0e6aa62cb93159c074abe35dda6a551c8b60f5c5d8e0fe3cfecadaed"
            }
            response = requests.get(url, headers=headers, cookies=cookies, allow_redirects=False)

            room_id = response.headers.get("location").split("?")[0].split("/")[-2]
            return room_id

        def detail(vid):
            headers = {
                "Host": "api5-core-hj.amemv.com",
                "x-tt-request-tag": "t=1;n=0;s=-1;p=0",
                "x-tt-dt": "AAA3ILDLDBQKHLCQWUR7PMVJ6OI6YLD5A2KNGELB7PUSTPUCSFILPHPULPUEMS47VJVHYVK5R5CD7MUWKE6I6AXYJSHIGY6UPDRIM4FUJTJJHFGUTS56YTNQNVYOS",
                "activity_now_client": "1755089456142",
                "x-is-hit-mate": "2",
                "x-ss-req-ticket": "1742779563858",
                "x-bd-kmsv": "1",
                # "bd-ticket-guard-client-data": "eyJyZXFfY29udGVudCI6InRpY2tldCxwYXRoLHRpbWVzdGFtcCIsInRpbWVzdGFtcCI6MTc0Mjc3OTU2MywidHNfc2lnbiI6IiIsInRzX3NpZ25fcmVlIjoidHMuMS40MzhiZTk3NjE0YTA0MzdiMmVhZjIyMjMxMzE1NTVjMzZmNmQ2OTc1ZDZhMDNmZWNlZTVlZGNhYzdlMWYxMTI4YzRmYmU4N2QyMzE5Y2YwNTMxODYyNGNlZGExNDkxMWNhNDA2ZGVkYmViZWRkYjJlMzBmY2U4ZDRmYTAyNTc1ZCIsInJlcV9zaWduIjoiIiwicmVxX3NpZ25fcmVlIjoibENidkhaOWp5cmlrOWZNTVgzY3hkV3c3amZVU1R3MUw1LzNORHFlSWhmVVx1MDAzZCJ9",
                "bd-ticket-guard-display-os-version": "TP1A.220624.014",
                "sdk-version": "2",
                "bd-ticket-guard-version": "3",
                # "bd-ticket-guard-ree-public-key": "BBOTk0DNpiOjO5ZidT/+Qwo9K/Q329vAhyqJmOWImHR3vC5EMREW7jgRCBueGPsos/V+BnEWNYCnMCWvlnBlK8w=",
                "bd-ticket-guard-iteration-version": "3",
                # "x-tt-passport-mfa-token": "CjMHyS9h+K88GHK0uupESM3lXQABbnG0GfBvgwzMFqYOXSNgvb2QOOTJ+4DwIdpMgVsHgqcaSgo8AAAAAAAAAAAAAE8uRaMYoyek2XxH02JjFqaR84kOpgqsZwd3tsk7zADbcGU944ErcgJE/oWcgQ4N0SiCENvP9Q0Y9rHRbCACIgEDYhdodA==",
                # "x-tt-token": "003eec35ecfed7854d0181a14fddf4cc6b009ddf327405a8b5d50b4423c3b9ccecb954a82e073780e0ad79480dc7c8c0430bf9f46667653c3b2f5988eb81e5de2a4610382e7a68e330dc20a53bbd528d4b6d8dfc20187f8c78da82174f904ed46f2b8--0a490a200ad321e2c41728fecebf35c94542bae98b0f935eab7c0973b2f071ccf8c39d771220e6ee70e856c9413a7b3a480eb5ef1aae92a68f1447266e65573ad0e5fccf586e18f6b4d309-3.0.1",
                # "x-tt-token-supplement": "01e332c5198ebe574b4046eca670e27906a1e3b6a6129de5050f65e80f5cb841d0d183e416bc58a268baf463caf1bb8d11b09737a750672b5ea89631db743ac8eb3",
                "passport-sdk-version": "601138",
                "x-vc-bdturing-sdk-version": "4.0.2.cn",
                "x-tt-store-region": "cn-gz",
                "x-tt-store-region-src": "uid",
                "x-ss-dp": "1128",
                "x-tt-trace-id": "01-c5c1c0fc0ca268537427ae17ecfa0468-c5c1c0fc0ca26853-00",
                "user-agent": "com.ss.android.ugc.aweme/350501 (Linux; U; Android 13; zh_CN_#Hans; Pixel 4; Build/TP1A.220624.014; Cronet/TTNetVersion:0936b3ee 2025-07-23 QuicVersion:40cc763c 2025-07-01)",
                "ttzip-version": "41059",
                # "x-argus": "J98kZw==",
                # "x-gorgon": "8404d0c500012ac915e139613ab42f24a9a7984cb248619f0f59",
                # "x-helios": "WFxWJr5LgZszOmGWmZMaZsjrhYliiMp16ITcc1SJyyMm81gm",
                # "x-khronos": "1730469671",
                # "x-ladon": "ZyTfJw==",
                # "x-medusa": "It8kZwqUa61uqikkGGqKSwWy6DFJDAABdTVw6qwIgSgDGMbBsa1oFLwcXP5ResnaU+IY98V7Jb6HzNe48EmGpptMnGlfHRXNPGaLqtBEicM0HN2jNfLgpqtJUR4/XZ9hOx/T57x40VqpNiQm1IcSuPuO22DMlbEzymb9lnAg/OiGaB0dt6n9O95VaMOP9ne3p8MWmDYOZkyt+liyWv3Fv+LDXcOMYmgyc2XUUBGoFZ8uFJ1cMgH/vYn3KjIoppppJAZFGk+d6Ri6sTtSIU6EpD5eYA79BdsVNFffPcfc4WoJ39dA3t2tCfm8RjAQ7+Dc00j3xZDO1+50lkcBjZnP1AdZ5lqFO0AhOOJPV8bvMfDqohLK8wYZNTEQRcBVoGibq/TBqSlFtqEI62fFuKXZ9OOZL85Duej7BqeW40OtADeN02gkGWgZF2d6hQGvdWZlAt/wkV9Gf1UDzvEW5IQWvl8INA2HTHt16PReMfetEPw23j5rNPuI6Cabk8KoszM1noWmoZWlh5ZqPe3x6BlcSDLdBGn+a7TRXFH0U9klxwyWhK5ja9NnYO0sigeiuBLxpZW5SRnwN8B6zY1IrvffytNlhWXu/YXPkQ4I9RumRL27r9oSstqtK64H2y3u7oSgvdzavYTZTpNy+4RqLGonBjHb7TOEtI11Adx8uaxn95NLqtbGgTGeWkNlf0kcooFb1E6D+smhNilV2R2P0x/4MjRfZvsB5/5uV2eDtCBXVOPJBhKPjh+s9CG+51Czt1bz+EZ0wBzy79bEwh+fs3NCq/evWYkNXmXWWGM1qor10lagWGhoGIIK8kMVeHnyz+NTk91lm5MNNl+phl1jC/WnCIMQ3iofh3XCQ1jURhsIpRDL+lS4cZJTIPAahUQ1j9Uh05AykDehgc31T014BS+58kHHCuicVEl2cMSGg2SiAmv203VICalay8FHtKfOzQMKyrem3g+MemA+hh+3WIEyz3CmJKUlmtBXLUFC6A11ieJZUG7gRrBf1dYMqfokQgNi7f7S43lvlFo2BqtYe+mlxF9yeaKVWZl0Wf0vP8zj//vHb//7xm+HEw==",
                # "x-soter": "AAEAAgABAgICAwIEAgUCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            }
            url = "https://api5-normal.amemv.com/aweme/v1/aweme/detail/"
            params = {
                "aweme_id": vid,
                "origin_type": "link",
                "request_source": "140",
                "is_story": "0",
                "location_permission": "1",
                "aweme_type": "1",
                "recommend_collect_feedback": "0",
                "from_push": "0",
                "item_level": "0",
                "group_id": "",
                "iid": "2241256972728228",
                "device_id": "2219294098199240",
                "ac": "wifi",
                "channel": "douyinweb1_64",
                "aid": "1128",
                "app_name": "aweme",
                "version_code": "270500",
                "version_name": "27.5.0",
                "device_platform": "android",
                "os": "android",
                "ssmix": "a",
                "device_type": "MI 8 SE",
                "device_brand": "Xiaomi",
                "language": "zh",
                "os_api": "29",
                "os_version": "10",
                "openudid": "6699c1962945d5e5",
                "manifest_version_code": "270501",
                "resolution": "1080*2115",
                "dpi": "440",
                "update_version_code": "27509900",
                "_rticket": "1721031866424",
                "package": "com.ss.android.ugc.aweme",
                "first_launch_timestamp": "1721031640",
                "last_deeplink_update_version_code": "0",
                "cpu_support64": "true",
                "host_abi": "arm64-v8a",
                "is_guest_mode": "0",
                "app_type": "normal",
                "minor_status": "0",
                "appTheme": "light",
                "need_personal_recommend": "1",
                "is_android_pad": "0",
                "is_android_fold": "0",
                "ts": "1721031866",
                "cdid": "4e4880da-ca91-41e7-98c8-646d595ac31d",
                "oaid": "fb0fcebe0e1a32ad"
            }

            response = requests.options(url, headers=headers, params=params, timeout=10)

            return response.json()["aweme_detail"]["video"]["play_addr_h264"]["url_list"][3]

        if not REQUESTS_AVAILABLE:
            self.log_status("错误: requests 库未安装，无法下载视频")
            self.show_popup("错误", "requests 库未安装，请检查应用配置")
            return

        url_text = self.url_input.text.strip()

        if not url_text:
            self.log_status("错误：请输入视频 URL")
            return

        # 从输入文本中提取 URL
        vurl = self.extract_url_from_text(url_text)
        # 检查 URL 是否为视频
        if not self.is_video_url(vurl):
            url = detail(get_vid(vurl))
        else:
            url = vurl

        if not url:
            self.log_status("错误：未找到有效的 URL")
            return

        if self.downloading:
            self.log_status("错误：当前正在下载中，请等待完成")
            return

        self.downloading = True
        self.current_url = url
        self.download_btn.disabled = True
        self.download_btn.text = "下载中..."
        self.download_btn.background_color = (0.5, 0.5, 0.5, 1)
        self.progress_bar.value = 0
        self.progress_label.text = ""

        self.log_status(f"开始下载: {url}")
        self.log_status("正在检查链接是否为视频...")

        # 在后台线程中执行下载
        self.download_thread = threading.Thread(target=self.download_video, args=(url,))
        self.download_thread.daemon = True
        self.download_thread.start()

    def confirm_paste(self, url, popup):
        """确认粘贴 URL"""
        self.url_input.text = url
        popup.dismiss()
        self.log_status(f"已从剪贴板提取 URL: {url}")

    def download_video(self, url):
        """下载视频的主要逻辑"""
        try:
            # 记录开始时间
            self.start_time = time.time()

            # 检查 URL 是否为视频
            if not self.is_video_url(url):
                self.log_status("警告: 这可能不是视频链接，已停止下载...")
                return False

            # 获取文件名
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            if not filename or '.' not in filename:
                filename = f"video_{int(time.time())}.mp4"

            filepath = os.path.join(self.download_path, filename)

            # 发送请求下载文件
            self.update_status("正在连接服务器...")
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()

            # 获取文件大小
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            self.update_status(f"文件大小: {self.format_file_size(total_size)}")
            self.update_status("开始下载...")

            # 写入文件
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        # 更新进度
                        current_time = time.time()
                        time_elapsed = current_time - self.start_time

                        if total_size > 0:
                            percent = int((downloaded_size / total_size) * 100)
                            self.update_progress(percent)

                            # 避免除以零错误
                            if time_elapsed > 0:
                                speed = downloaded_size / time_elapsed
                                speed_str = self.format_speed(speed)
                            else:
                                speed_str = "计算中..."

                            self.update_progress_label(f"{percent}% - {speed_str}")
                        else:
                            # 如果无法获取总大小，只显示已下载大小
                            if time_elapsed > 0:
                                speed = downloaded_size / time_elapsed
                                speed_str = self.format_speed(speed)
                            else:
                                speed_str = "计算中..."

                            self.update_progress_label(
                                f"已下载: {self.format_file_size(downloaded_size)} - {speed_str}")

            # 下载完成
            self.update_progress(100)
            self.update_progress_label("100% - 下载完成")
            self.update_status(f"下载完成: {filename}")

            # 添加到相册（Android）
            if platform == 'android':
                self.add_to_gallery(filepath)

            self.download_complete()

        except Exception as e:
            error_msg = f"下载失败: {str(e)}"
            print(f"下载错误: {e}")
            self.download_failed(error_msg)

    def format_file_size(self, size_bytes):
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.2f} {size_names[i]}"

    def format_speed(self, speed_bytes):
        """格式化速度显示"""
        if speed_bytes >= 1024 * 1024:
            return f"{speed_bytes / (1024 * 1024):.1f} MB/s"
        elif speed_bytes >= 1024:
            return f"{speed_bytes / 1024:.1f} KB/s"
        else:
            return f"{speed_bytes:.1f} B/s"

    @mainthread
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.value = value

    @mainthread
    def update_progress_label(self, text):
        """更新进度标签"""
        self.progress_label.text = text

    @mainthread
    def update_status(self, message):
        """更新状态信息"""
        self.log_status(message)

    @mainthread
    def download_complete(self):
        """下载完成处理"""
        self.downloading = False
        self.download_btn.disabled = False
        self.download_btn.text = "开始下载"
        self.download_btn.background_color = (0.2, 0.7, 0.3, 1)

        self.log_status("下载完成！")
        self.show_popup("下载成功", "视频已成功下载到文件夹！")

    @mainthread
    def download_failed(self, message):
        """下载失败处理"""
        self.downloading = False
        self.download_btn.disabled = False
        self.download_btn.text = "开始下载"
        self.download_btn.background_color = (0.2, 0.7, 0.3, 1)
        self.progress_label.text = ""

        self.log_status(message)
        self.show_popup("下载失败", message)

    def add_to_gallery(self, filepath):
        """将下载的视频添加到相册（Android）"""
        try:
            from jnius import autoclass
            MediaScannerConnection = autoclass('android.media.MediaScannerConnection')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            # 扫描下载的文件
            MediaScannerConnection.scanFile(
                PythonActivity.mActivity,
                [filepath],
                None,
                None
            )

            self.log_status("视频已添加到相册")
        except Exception as e:
            self.log_status(f"添加到相册失败: {str(e)}")

    def log_status(self, message):
        """更新状态显示"""
        try:
            if isinstance(message, bytes):
                message = message.decode('utf-8')

            timestamp = self.get_current_time()
            formatted_message = f"[{timestamp}] {message}"

            # 使用自动滚动的标签添加文本
            self.status_scroll.add_text(formatted_message)
        except Exception as e:
            print(f"更新状态时出错: {e}")

    def get_current_time(self):
        """获取当前时间字符串"""
        return datetime.now().strftime("%H:%M:%S")

    def show_popup(self, title, message):
        """显示弹窗"""
        content = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))

        message_label = Label(text=message)
        font_manager.apply_font(message_label)
        content.add_widget(message_label)

        btn = Button(
            text='确定',
            size_hint_y=None,
            height=dp(40),
            background_color=(0.3, 0.5, 0.8, 1),
            color=(1, 1, 1, 1)
        )
        font_manager.apply_font(btn)

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.7, 0.3)
        )
        btn.bind(on_press=popup.dismiss)
        content.add_widget(btn)
        popup.open()


if __name__ == '__main__':
    # Windows 控制台编码设置
    if sys.platform == 'win32':
        try:
            import io

            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        except:
            pass

    VideoDownloaderApp().run()