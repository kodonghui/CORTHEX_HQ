"""
다음 카페 퍼블리셔 (Selenium 기반).

다음 카페 공식 글쓰기 API가 없어 Selenium 브라우저 자동화를 사용합니다.
- 카카오 계정 로그인
- 카페 게시글 작성 (제목 + 본문)
- cafe_id/board_id는 환경변수 또는 PostContent.extra로 지정
- 주의: API 기반 퍼블리셔보다 안정성이 낮을 수 있습니다. UI 변경 시 셀렉터 업데이트 필요.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult
from src.tools.sns.browser_utils import SNSBrowserManager, random_delay

logger = logging.getLogger("corthex.sns.daum_cafe")

KAKAO_LOGIN_URL = "https://accounts.kakao.com/login/"
CAFE_WRITE_URL = "https://cafe.daum.net/{cafe_id}/_write"
CAFE_WRITE_BOARD_URL = "https://cafe.daum.net/{cafe_id}/_write?board_id={board_id}"


class DaumCafePublisher(BasePublisher):
    """다음 카페 Selenium 기반 퍼블리셔.

    공식 글쓰기 API가 없어 Selenium 자동화를 사용합니다.
    카카오 계정 로그인이 필요합니다.
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

    async def check_connection(self) -> bool:
        """Selenium 기반이므로 credential 존재 여부로 확인."""
        return bool(self.kakao_id and self.kakao_pw)

    async def publish(self, content: PostContent) -> PublishResult:
        if not self.kakao_id or not self.kakao_pw:
            return PublishResult(
                success=False,
                platform=self.platform,
                message="KAKAO_ID, KAKAO_PW 환경변수가 필요합니다.",
            )

        cafe_id = content.extra.get("cafe_id") or self.default_cafe_id
        board_id = content.extra.get("board_id") or self.default_board_id

        if not cafe_id:
            return PublishResult(
                success=False,
                platform=self.platform,
                message="cafe_id가 필요합니다. 환경변수(DAUM_CAFE_ID) 또는 extra에 지정하세요.",
            )

        try:
            return await asyncio.to_thread(
                self._publish_sync, content, cafe_id, board_id
            )
        except Exception as e:
            logger.error("[DaumCafe] 발행 실패: %s", e)
            return PublishResult(
                success=False,
                platform=self.platform,
                message=f"Selenium 오류: {e}",
            )

    def _publish_sync(
        self, content: PostContent, cafe_id: str, board_id: str
    ) -> PublishResult:
        """동기 Selenium 발행 플로우 (asyncio.to_thread로 실행)."""
        browser = SNSBrowserManager(headless=self._headless)
        try:
            driver = browser.driver

            # 1. 카카오 로그인
            if not self._login(browser, cafe_id):
                return PublishResult(
                    success=False,
                    platform=self.platform,
                    message="카카오 로그인 실패",
                )

            # 2. 글쓰기 페이지 이동
            if board_id:
                write_url = CAFE_WRITE_BOARD_URL.format(
                    cafe_id=cafe_id, board_id=board_id
                )
            else:
                write_url = CAFE_WRITE_URL.format(cafe_id=cafe_id)

            driver.get(write_url)
            random_delay(3.0, 5.0)

            wait = WebDriverWait(driver, 20)

            # 3. iframe 처리 (다음 카페는 에디터가 iframe 안에 있을 수 있음)
            try:
                driver.switch_to.frame("down")
            except Exception:
                pass

            # 4. 제목 입력
            try:
                title_input = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR,
                         "input.title_input, input[name='title'], "
                         "input#title, input[placeholder*='제목']")
                    )
                )
                title_input.clear()
                title_input.send_keys(content.title)
            except TimeoutException:
                # Fallback: xpath
                try:
                    title_el = driver.find_element(
                        By.XPATH, "//input[contains(@class, 'title') or @name='title']"
                    )
                    title_el.clear()
                    title_el.send_keys(content.title)
                except Exception as e:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        message=f"제목 입력 영역을 찾을 수 없습니다: {e}",
                    )

            random_delay(0.5, 1.0)

            # 5. 본문 입력 (다음 에디터는 iframe 내 iframe일 수 있음)
            body_filled = False

            # 방법 1: tx_canvas iframe (Daum 리치 에디터)
            try:
                editor_iframe = driver.find_element(By.CSS_SELECTOR, "iframe.tx_canvas")
                driver.switch_to.frame(editor_iframe)
                editor_body = driver.find_element(By.CSS_SELECTOR, "body")
                editor_body.click()
                random_delay(0.3, 0.5)

                if "<" in content.body and ">" in content.body:
                    driver.execute_script(
                        "document.body.innerHTML = arguments[0];", content.body
                    )
                else:
                    editor_body.send_keys(content.body)

                driver.switch_to.parent_frame()
                body_filled = True
            except Exception:
                pass

            # 방법 2: contenteditable div
            if not body_filled:
                try:
                    body_area = driver.find_element(
                        By.CSS_SELECTOR,
                        "div.tx-content-container, div[contenteditable='true']"
                    )
                    body_area.click()
                    random_delay(0.3, 0.5)
                    body_area.send_keys(content.body)
                    body_filled = True
                except Exception:
                    pass

            # 방법 3: textarea fallback
            if not body_filled:
                try:
                    textarea = driver.find_element(
                        By.CSS_SELECTOR, "textarea#content, textarea.content_area, textarea"
                    )
                    textarea.send_keys(content.body)
                    body_filled = True
                except Exception as e:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        message=f"본문 입력 영역을 찾을 수 없습니다: {e}",
                    )

            random_delay(1.0, 2.0)

            # 6. 등록 버튼 클릭
            try:
                submit_btn = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR,
                         "button.btn_submit, button#btn_write, "
                         "a.btn_submit, button[type='submit']")
                    )
                )
                submit_btn.click()
            except TimeoutException:
                try:
                    btn = driver.find_element(
                        By.XPATH,
                        "//button[contains(text(), '등록') or contains(text(), '작성') or contains(text(), '올리기')]"
                    )
                    btn.click()
                except Exception as e:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        message=f"등록 버튼을 찾을 수 없습니다: {e}",
                    )

            random_delay(3.0, 5.0)

            # 7. 결과 확인
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

            current_url = driver.current_url
            if cafe_id in current_url and "_write" not in current_url:
                post_id = current_url.rstrip("/").split("/")[-1]
                logger.info("[DaumCafe] 글 발행 성공: %s", current_url)
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    post_id=post_id,
                    post_url=current_url,
                    message="다음 카페 글 발행 완료",
                )

            return PublishResult(
                success=False,
                platform=self.platform,
                message=f"발행 후 URL 확인 실패. 현재 URL: {current_url}",
            )

        finally:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            browser.quit()

    def _login(self, browser: SNSBrowserManager, cafe_id: str) -> bool:
        """카카오 로그인. leet-opinion-scraper/scraper/daum_cafe.py 패턴."""
        driver = browser.driver

        # 쿠키 먼저 시도
        driver.get(f"https://cafe.daum.net/{cafe_id}")
        random_delay(1.0, 2.0)
        if browser.load_cookies("kakao"):
            driver.refresh()
            random_delay(2.0, 3.0)
            if self._is_logged_in(driver):
                logger.info("[DaumCafe] 쿠키 로그인 성공")
                return True

        # 카카오 계정으로 로그인
        try:
            login_url = f"{KAKAO_LOGIN_URL}?continue=https://cafe.daum.net/{cafe_id}"
            driver.get(login_url)
            random_delay(2.0, 3.0)

            wait = WebDriverWait(driver, 15)

            id_input = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[name='loginId'], input#loginId")
                )
            )
            id_input.clear()
            id_input.send_keys(self.kakao_id)

            pw_input = driver.find_element(
                By.CSS_SELECTOR, "input[name='password'], input#password"
            )
            pw_input.clear()
            pw_input.send_keys(self.kakao_pw)

            login_btn = driver.find_element(
                By.CSS_SELECTOR, "button[type='submit'], button.btn_confirm"
            )
            login_btn.click()
            random_delay(4.0, 6.0)

            # 로그인 확인
            driver.get(f"https://cafe.daum.net/{cafe_id}")
            random_delay(2.0, 3.0)

            if self._is_logged_in(driver):
                browser.save_cookies("kakao")
                logger.info("[DaumCafe] 로그인 성공")
                return True

            logger.error("[DaumCafe] 로그인 실패")
            return False

        except Exception as e:
            logger.error("[DaumCafe] 로그인 예외: %s", e)
            return False

    def _is_logged_in(self, driver: Any) -> bool:
        try:
            page = driver.page_source
            return "로그아웃" in page or "my_profile" in page or "logout" in page.lower()
        except Exception:
            return False

    async def delete(self, post_id: str) -> bool:
        logger.warning("[DaumCafe] Selenium 기반 삭제는 현재 미지원입니다.")
        return False
