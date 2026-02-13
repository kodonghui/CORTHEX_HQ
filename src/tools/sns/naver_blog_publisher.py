"""
네이버 블로그 퍼블리셔 (Selenium 기반).

네이버 블로그 Open API는 2020년 5월 이후 중단되어 Selenium 브라우저 자동화를 사용합니다.
- 네이버 로그인 (credential 기반, JS 인젝션)
- 블로그 글 작성 (SmartEditor)
- 주의: API 기반 퍼블리셔보다 안정성이 낮을 수 있습니다. UI 변경 시 셀렉터 업데이트 필요.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult
from src.tools.sns.browser_utils import SNSBrowserManager, random_delay

logger = logging.getLogger("corthex.sns.naver_blog")

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
BLOG_WRITE_URL = "https://blog.naver.com/{blog_id}/postwrite"


class NaverBlogPublisher(BasePublisher):
    """네이버 블로그 Selenium 기반 퍼블리셔.

    공식 API 폐지로 Selenium 자동화를 사용합니다.
    CAPTCHA/2FA 발생 시 수동 개입이 필요할 수 있습니다.
    """

    platform = "naver_blog"

    def __init__(self, oauth: Any) -> None:
        super().__init__(oauth)
        self._headless = os.getenv("SNS_BROWSER_HEADLESS", "true").lower() == "true"

    @property
    def naver_id(self) -> str:
        return os.getenv("NAVER_ID", "")

    @property
    def naver_pw(self) -> str:
        return os.getenv("NAVER_PW", "")

    @property
    def blog_id(self) -> str:
        return os.getenv("NAVER_BLOG_ID", "") or self.naver_id

    async def check_connection(self) -> bool:
        """Selenium 기반이므로 credential 존재 여부로 확인."""
        return bool(self.naver_id and self.naver_pw)

    async def publish(self, content: PostContent) -> PublishResult:
        if not self.naver_id or not self.naver_pw:
            return PublishResult(
                success=False,
                platform=self.platform,
                message="NAVER_ID, NAVER_PW 환경변수가 필요합니다.",
            )

        try:
            return await asyncio.to_thread(self._publish_sync, content)
        except Exception as e:
            logger.error("[NaverBlog] 발행 실패: %s", e)
            return PublishResult(
                success=False,
                platform=self.platform,
                message=f"Selenium 오류: {e}",
            )

    def _publish_sync(self, content: PostContent) -> PublishResult:
        """동기 Selenium 발행 플로우 (asyncio.to_thread로 실행)."""
        browser = SNSBrowserManager(headless=self._headless)
        try:
            driver = browser.driver

            # 1. 네이버 로그인
            if not self._login(browser):
                return PublishResult(
                    success=False,
                    platform=self.platform,
                    message="네이버 로그인 실패",
                )

            # 2. 블로그 글쓰기 페이지 이동
            write_url = BLOG_WRITE_URL.format(blog_id=self.blog_id)
            driver.get(write_url)
            random_delay(3.0, 5.0)

            wait = WebDriverWait(driver, 20)

            # 3. 제목 입력
            try:
                title_area = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.se-documentTitle-editView .se-text-paragraph")
                    )
                )
                title_area.click()
                random_delay(0.3, 0.5)
                title_area.send_keys(content.title)
            except TimeoutException:
                # Fallback: 다른 에디터 버전
                try:
                    title_input = driver.find_element(
                        By.CSS_SELECTOR, "textarea.se_textarea, input[placeholder*='제목']"
                    )
                    title_input.send_keys(content.title)
                except Exception as e:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        message=f"제목 입력 영역을 찾을 수 없습니다: {e}",
                    )

            random_delay(0.5, 1.0)

            # 4. 본문 입력
            try:
                body_area = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.se-component-content .se-text-paragraph")
                    )
                )
                body_area.click()
                random_delay(0.3, 0.5)

                # HTML 콘텐츠면 JS로 삽입, 아니면 send_keys
                if "<" in content.body and ">" in content.body:
                    driver.execute_script(
                        """
                        var container = arguments[0].closest('.se-component-content');
                        if (container) {
                            container.querySelector('.se-text-paragraph').innerHTML = arguments[1];
                        }
                        """,
                        body_area,
                        content.body,
                    )
                else:
                    body_area.send_keys(content.body)
            except TimeoutException:
                # Fallback
                try:
                    body_el = driver.find_element(
                        By.CSS_SELECTOR, "div[contenteditable='true'], textarea.se_textarea"
                    )
                    body_el.click()
                    body_el.send_keys(content.body)
                except Exception as e:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        message=f"본문 입력 영역을 찾을 수 없습니다: {e}",
                    )

            random_delay(1.0, 2.0)

            # 5. 태그 입력
            if content.tags:
                self._set_tags(driver, content.tags)

            # 6. 발행 버튼 클릭
            try:
                publish_btn = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button.publish_btn__Y9, button[data-testid='publish-btn'], button.se-publish-btn")
                    )
                )
                publish_btn.click()
            except TimeoutException:
                # Fallback: 다양한 발행 버튼 패턴
                try:
                    btn = driver.find_element(
                        By.XPATH, "//button[contains(text(), '발행') or contains(text(), '등록') or contains(text(), '공개')]"
                    )
                    btn.click()
                except Exception as e:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        message=f"발행 버튼을 찾을 수 없습니다: {e}",
                    )

            random_delay(3.0, 5.0)

            # 7. 확인 다이얼로그 처리
            try:
                confirm_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button.confirm_btn, button.se-popup-button-yes")
                    )
                )
                confirm_btn.click()
                random_delay(3.0, 5.0)
            except TimeoutException:
                pass  # 확인 다이얼로그 없음

            # 8. 발행 결과 확인
            current_url = driver.current_url
            if "blog.naver.com" in current_url and "postwrite" not in current_url:
                post_id = current_url.rstrip("/").split("/")[-1]
                logger.info("[NaverBlog] 글 발행 성공: %s", current_url)
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    post_id=post_id,
                    post_url=current_url,
                    message="네이버 블로그 글 발행 완료",
                )

            return PublishResult(
                success=False,
                platform=self.platform,
                message=f"발행 후 URL 확인 실패. 현재 URL: {current_url}",
            )

        finally:
            browser.quit()

    def _login(self, browser: SNSBrowserManager) -> bool:
        """네이버 로그인. leet-opinion-scraper/scraper/naver_cafe.py 패턴."""
        driver = browser.driver

        # 쿠키 먼저 시도
        driver.get("https://www.naver.com/")
        random_delay(1.0, 2.0)
        if browser.load_cookies("naver"):
            driver.refresh()
            random_delay(2.0, 3.0)
            if self._is_logged_in(driver):
                logger.info("[NaverBlog] 쿠키 로그인 성공")
                return True

        # JS 인젝션으로 로그인 (봇 탐지 우회)
        driver.get(NAVER_LOGIN_URL)
        random_delay(2.0, 3.0)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#id"))
            )

            driver.execute_script(
                f"document.querySelector('input#id').value = '{self.naver_id}';"
            )
            random_delay(0.3, 0.5)
            driver.execute_script(
                f"document.querySelector('input#pw').value = '{self.naver_pw}';"
            )
            random_delay(0.3, 0.5)

            login_btn = driver.find_element(
                By.CSS_SELECTOR, "button#log\\.login, button.btn_login, input.btn_login"
            )
            login_btn.click()
            random_delay(4.0, 6.0)

            # CAPTCHA/2FA 대기
            if "nidlogin" in driver.current_url:
                logger.warning("[NaverBlog] CAPTCHA/2FA 필요. 60초 대기합니다.")
                for _ in range(12):
                    time.sleep(5)
                    if "nidlogin" not in driver.current_url:
                        break

            if self._is_logged_in(driver):
                browser.save_cookies("naver")
                logger.info("[NaverBlog] 로그인 성공")
                return True

            logger.error("[NaverBlog] 로그인 실패")
            return False

        except Exception as e:
            logger.error("[NaverBlog] 로그인 예외: %s", e)
            return False

    def _is_logged_in(self, driver: Any) -> bool:
        try:
            page = driver.page_source
            return "로그아웃" in page or "gnb_my" in page or "MyInfo" in page
        except Exception:
            return False

    def _set_tags(self, driver: Any, tags: list[str]) -> None:
        try:
            tag_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input.se-tag-input, input[placeholder*='태그']")
                )
            )
            for tag in tags:
                tag_input.send_keys(tag)
                tag_input.send_keys(Keys.ENTER)
                random_delay(0.2, 0.4)
        except TimeoutException:
            logger.warning("[NaverBlog] 태그 입력 영역을 찾을 수 없습니다.")

    async def delete(self, post_id: str) -> bool:
        logger.warning("[NaverBlog] Selenium 기반 삭제는 현재 미지원입니다.")
        return False
