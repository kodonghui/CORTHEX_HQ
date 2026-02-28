"""
다음 카페 퍼블리셔 (Selenium 기반).

다음 카페 공식 글쓰기 API가 없어 Selenium 브라우저 자동화를 사용합니다.
- 카카오 계정 로그인 (logins.daum.net → 카카오 OAuth)
- 글쓰기 URL: /_c21_/united_write?grpid={grpid}&fldid={board_id}
- 에디터: TinyMCE (iframe#keditorContainer_ifr)
- 검증: 2026-02-28 cafe.daum.net/snuleet (서로연)에서 발행 성공 확인
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult
from src.tools.sns.browser_utils import SNSBrowserManager, random_delay

logger = logging.getLogger("corthex.sns.daum_cafe")

DAUM_LOGIN_URL = "https://logins.daum.net/accounts/oauth/login.do"


class DaumCafePublisher(BasePublisher):
    """다음 카페 Selenium 기반 퍼블리셔.
    로그인: logins.daum.net → '카카오로 로그인' → accounts.kakao.com
    """

    platform = "daum_cafe"

    def __init__(self, oauth: Any) -> None:
        super().__init__(oauth)
        self._headless = os.getenv("SNS_BROWSER_HEADLESS", "true").lower() == "true"

    @property
    def kakao_id(self) -> str:
        return os.getenv("DAUM_KAKAO_ID", "") or os.getenv("KAKAO_ID", "")

    @property
    def kakao_pw(self) -> str:
        return os.getenv("DAUM_KAKAO_PW", "") or os.getenv("KAKAO_PW", "")

    @property
    def default_cafe_id(self) -> str:
        return os.getenv("DAUM_CAFE_ID", "")

    @property
    def default_board_id(self) -> str:
        return os.getenv("DAUM_CAFE_BOARD_ID", "")

    @property
    def default_grpid(self) -> str:
        return os.getenv("DAUM_CAFE_GRPID", "")

    async def check_connection(self) -> bool:
        return bool(self.kakao_id and self.kakao_pw)

    async def publish(self, content: PostContent) -> PublishResult:
        if not self.kakao_id or not self.kakao_pw:
            return PublishResult(success=False, platform=self.platform, message="KAKAO_ID, KAKAO_PW 환경변수가 필요합니다.")
        cafe_id = content.extra.get("cafe_id") or self.default_cafe_id
        board_id = content.extra.get("board_id") or self.default_board_id
        grpid = content.extra.get("grpid") or self.default_grpid
        if not cafe_id:
            return PublishResult(success=False, platform=self.platform, message="cafe_id가 필요합니다.")
        try:
            return await asyncio.to_thread(self._publish_sync, content, cafe_id, board_id, grpid)
        except Exception as e:
            logger.error("[DaumCafe] 발행 실패: %s", e)
            return PublishResult(success=False, platform=self.platform, message=f"Selenium 오류: {e}")

    def _publish_sync(self, content: PostContent, cafe_id: str, board_id: str, grpid: str) -> PublishResult:
        browser = SNSBrowserManager(headless=self._headless)
        try:
            driver = browser.driver
            if not self._login(browser, cafe_id):
                return PublishResult(success=False, platform=self.platform, message="카카오 로그인 실패")

            if not grpid:
                grpid = self._discover_grpid(driver, cafe_id)
            if not grpid:
                return PublishResult(success=False, platform=self.platform, message="grpid를 확인할 수 없습니다. DAUM_CAFE_GRPID 환경변수를 설정하세요.")

            write_url = f"https://cafe.daum.net/_c21_/united_write?grpid={grpid}"
            if board_id:
                write_url += f"&fldid={board_id}"
            driver.get(write_url)
            random_delay(3.0, 5.0)

            try:
                driver.switch_to.frame("down")
            except Exception:
                pass

            wait = WebDriverWait(driver, 20)

            # 제목 입력
            try:
                title_input = wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[placeholder='제목을 입력하세요.']")
                ))
                title_input.clear()
                title_input.send_keys(content.title)
            except TimeoutException:
                try:
                    title_el = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='제목'], input[name='title']")
                    title_el.clear()
                    title_el.send_keys(content.title)
                except Exception as e:
                    return PublishResult(success=False, platform=self.platform, message=f"제목 입력 영역을 찾을 수 없습니다: {e}")

            random_delay(0.5, 1.0)

            # 본문 입력 (TinyMCE)
            body_filled = False
            try:
                editor_iframe = driver.find_element(By.CSS_SELECTOR, "iframe#keditorContainer_ifr")
                driver.switch_to.frame(editor_iframe)
                editor_body = driver.find_element(By.CSS_SELECTOR, "body#tinymce, body")
                editor_body.click()
                random_delay(0.3, 0.5)
                if "<" in content.body and ">" in content.body:
                    driver.execute_script("document.body.innerHTML = arguments[0];", content.body)
                else:
                    editor_body.send_keys(content.body)
                driver.switch_to.parent_frame()
                body_filled = True
            except Exception:
                try:
                    driver.switch_to.parent_frame()
                except Exception:
                    pass

            if not body_filled:
                try:
                    editor_iframe = driver.find_element(By.CSS_SELECTOR, "iframe.tx_canvas")
                    driver.switch_to.frame(editor_iframe)
                    editor_body = driver.find_element(By.CSS_SELECTOR, "body")
                    editor_body.click()
                    editor_body.send_keys(content.body)
                    driver.switch_to.parent_frame()
                    body_filled = True
                except Exception:
                    try:
                        driver.switch_to.parent_frame()
                    except Exception:
                        pass

            if not body_filled:
                try:
                    body_area = driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true']")
                    body_area.click()
                    body_area.send_keys(content.body)
                except Exception as e:
                    return PublishResult(success=False, platform=self.platform, message=f"본문 입력 영역을 찾을 수 없습니다: {e}")

            random_delay(1.0, 2.0)

            # "등록" 버튼 클릭
            try:
                submit_btn = None
                for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                    if btn.text.strip() == "등록" and btn.is_displayed():
                        submit_btn = btn
                        break
                if submit_btn:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", submit_btn)
                    random_delay(0.3, 0.5)
                    submit_btn.click()
                else:
                    driver.find_element(By.XPATH, "//button[contains(text(), '등록')]").click()
            except Exception as e:
                return PublishResult(success=False, platform=self.platform, message=f"등록 버튼을 찾을 수 없습니다: {e}")

            random_delay(5.0, 8.0)

            # 결과 확인
            inner_url = driver.execute_script("return window.location.href")
            if "post_article" in inner_url or "bbs_read" in inner_url:
                datanum_match = re.search(r"datanum=(\d+)", inner_url)
                post_id = datanum_match.group(1) if datanum_match else ""
                post_url = f"https://cafe.daum.net/{cafe_id}/{board_id}/{post_id}" if post_id else ""
                logger.info("[DaumCafe] 글 발행 성공: %s", post_url or inner_url)
                return PublishResult(success=True, platform=self.platform, post_id=post_id, post_url=post_url, message="다음 카페 글 발행 완료")

            if "united_write" not in inner_url:
                return PublishResult(success=True, platform=self.platform, post_id="", post_url=f"https://cafe.daum.net/{cafe_id}/{board_id}", message="다음 카페 글 발행 완료 (글 URL 확인 필요)")

            return PublishResult(success=False, platform=self.platform, message=f"발행 후 URL 확인 실패. 현재 URL: {inner_url}")
        finally:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            browser.quit()

    def _login(self, browser: SNSBrowserManager, cafe_id: str) -> bool:
        driver = browser.driver
        driver.get(f"https://cafe.daum.net/{cafe_id}")
        random_delay(1.0, 2.0)
        if browser.load_cookies("daum"):
            driver.refresh()
            random_delay(2.0, 3.0)
            try:
                driver.switch_to.frame("down")
                if self._is_logged_in(driver):
                    logger.info("[DaumCafe] 쿠키 로그인 성공")
                    driver.switch_to.default_content()
                    return True
                driver.switch_to.default_content()
            except Exception:
                pass

        try:
            login_url = f"{DAUM_LOGIN_URL}?url=https://cafe.daum.net/{cafe_id}"
            driver.get(login_url)
            random_delay(2.0, 3.0)
            wait = WebDriverWait(driver, 15)
            kakao_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.login__container--btn-kakao")))
            kakao_btn.click()
            random_delay(3.0, 5.0)

            if "accounts.kakao.com" in driver.current_url:
                id_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='loginId']")))
                id_input.clear()
                id_input.send_keys(self.kakao_id)
                pw_input = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
                pw_input.clear()
                pw_input.send_keys(self.kakao_pw)
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                random_delay(5.0, 7.0)
                if "accounts.kakao.com" in driver.current_url:
                    logger.warning("[DaumCafe] 카카오톡 인증 대기 중 (60초)...")
                    for _ in range(12):
                        time.sleep(5)
                        if "accounts.kakao.com" not in driver.current_url:
                            break

            if "cafe.daum.net" in driver.current_url:
                browser.save_cookies("daum")
                logger.info("[DaumCafe] 로그인 성공")
                return True

            driver.get(f"https://cafe.daum.net/{cafe_id}")
            random_delay(2.0, 3.0)
            try:
                driver.switch_to.frame("down")
                if self._is_logged_in(driver):
                    browser.save_cookies("daum")
                    driver.switch_to.default_content()
                    return True
                driver.switch_to.default_content()
            except Exception:
                pass
            logger.error("[DaumCafe] 로그인 실패")
            return False
        except Exception as e:
            logger.error("[DaumCafe] 로그인 예외: %s", e)
            return False

    def _discover_grpid(self, driver: Any, cafe_id: str) -> str:
        try:
            driver.get(f"https://cafe.daum.net/{cafe_id}")
            random_delay(2.0, 3.0)
            down_iframe = driver.find_element(By.CSS_SELECTOR, "iframe[name='down']")
            src = down_iframe.get_attribute("src") or ""
            match = re.search(r"grpid=([A-Za-z0-9]+)", src)
            if match:
                logger.info("[DaumCafe] grpid 자동 발견: %s", match.group(1))
                return match.group(1)
            page = driver.page_source
            match = re.search(r"grpid=([A-Za-z0-9]+)", page)
            if match:
                return match.group(1)
        except Exception as e:
            logger.warning("[DaumCafe] grpid 추출 실패: %s", e)
        return ""

    def _is_logged_in(self, driver: Any) -> bool:
        try:
            page = driver.page_source
            return "로그아웃" in page or "my_profile" in page or "logout" in page.lower()
        except Exception:
            return False

    async def delete(self, post_id: str) -> bool:
        logger.warning("[DaumCafe] Selenium 기반 삭제는 현재 미지원입니다.")
        return False
