"""
Tistory 블로그 퍼블리셔 (Selenium 기반).

Tistory Open API는 2024년 2월 폐지되어 Selenium 브라우저 자동화를 사용합니다.
- 카카오 계정 로그인 (쿠키 재사용 지원)
- 블로그 글 작성 (제목 + 본문 + 태그)
- 공개/비공개 설정 (라디오 버튼 기반)
- 주의: UI 변경 시 셀렉터 업데이트 필요.
- 검증: 2026-02-28 corthex.tistory.com에서 공개 발행 성공 확인
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from src.tools.sns.base_publisher import BasePublisher, PostContent, PublishResult
from src.tools.sns.browser_utils import SNSBrowserManager, random_delay

logger = logging.getLogger("corthex.sns.tistory")

KAKAO_LOGIN_URL = "https://accounts.kakao.com/login/"


class TistoryPublisher(BasePublisher):
    """Tistory 블로그 Selenium 기반 퍼블리셔.

    Tistory Open API 폐지(2024.02)로 Selenium 자동화를 사용합니다.
    카카오 계정 로그인이 필요합니다.
    """

    platform = "tistory"

    def __init__(self, oauth: Any) -> None:
        super().__init__(oauth)
        self._headless = os.getenv("SNS_BROWSER_HEADLESS", "true").lower() == "true"

    @property
    def kakao_id(self) -> str:
        return os.getenv("KAKAO_ID", "")

    @property
    def kakao_pw(self) -> str:
        return os.getenv("KAKAO_PW", "")

    @property
    def blog_name(self) -> str:
        return os.getenv("TISTORY_BLOG_NAME", "")

    @property
    def write_url(self) -> str:
        if self.blog_name:
            return f"https://{self.blog_name}.tistory.com/manage/newpost"
        return ""

    async def check_connection(self) -> bool:
        """Selenium 기반이므로 credential 존재 여부로 확인."""
        return bool(self.kakao_id and self.kakao_pw and self.blog_name)

    async def publish(self, content: PostContent) -> PublishResult:
        if not self.kakao_id or not self.kakao_pw:
            return PublishResult(
                success=False,
                platform=self.platform,
                message="KAKAO_ID, KAKAO_PW 환경변수가 필요합니다.",
            )
        if not self.blog_name:
            return PublishResult(
                success=False,
                platform=self.platform,
                message="TISTORY_BLOG_NAME 환경변수가 필요합니다. (예: corthex)",
            )

        try:
            return await asyncio.to_thread(self._publish_sync, content)
        except Exception as e:
            logger.error("[Tistory] 발행 실패: %s", e)
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

            # 1. 카카오 로그인
            if not self._login(browser):
                return PublishResult(
                    success=False,
                    platform=self.platform,
                    message="카카오 로그인 실패",
                )

            # 2. 글쓰기 페이지 이동
            driver.get(self.write_url)
            random_delay(3.0, 5.0)

            # 2-1. 임시 저장 글 알림 처리
            try:
                alert = driver.switch_to.alert
                logger.info("[Tistory] 임시 저장 글 알림 닫기: %s", alert.text)
                alert.dismiss()  # '아니오' — 새 글로 작성
                random_delay(1.0, 2.0)
            except Exception:
                pass

            wait = WebDriverWait(driver, 20)

            # 3. 제목 입력 (textarea#post-title-inp)
            try:
                title_input = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR,
                         "textarea#post-title-inp, "
                         "textarea.textarea_tit, "
                         "input#post-title-inp, "
                         "input[name='title']")
                    )
                )
                title_input.clear()
                title_input.send_keys(content.title)
            except TimeoutException:
                try:
                    title_el = driver.find_element(
                        By.XPATH, "//textarea[contains(@class, 'textarea_tit')] | //input[contains(@placeholder, '제목')]"
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

            # 4. 본문 입력
            body_filled = False

            # 방법 1: TinyMCE iframe (editor-tistory_ifr)
            try:
                editor_frame = driver.find_element(
                    By.CSS_SELECTOR, "iframe#editor-tistory_ifr, iframe.mce-edit-area"
                )
                driver.switch_to.frame(editor_frame)
                editor_body = driver.find_element(By.CSS_SELECTOR, "body#tinymce, body")
                editor_body.click()
                random_delay(0.3, 0.5)

                if "<" in content.body and ">" in content.body:
                    driver.execute_script(
                        "document.body.innerHTML = arguments[0];", content.body
                    )
                else:
                    editor_body.send_keys(content.body)

                driver.switch_to.default_content()
                body_filled = True
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass

            # 방법 2: textarea fallback (editor-tistory)
            if not body_filled:
                try:
                    textarea = driver.find_element(
                        By.CSS_SELECTOR, "textarea#editor-tistory, textarea#content"
                    )
                    textarea.send_keys(content.body)
                    body_filled = True
                except Exception:
                    pass

            # 방법 3: contenteditable div
            if not body_filled:
                try:
                    body_div = driver.find_element(
                        By.CSS_SELECTOR, "div[contenteditable='true'], div.mce-content-body"
                    )
                    body_div.click()
                    body_div.send_keys(content.body)
                    body_filled = True
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

            # 6. "완료" 버튼 → 발행 레이어 열기
            try:
                publish_layer_btn = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button#publish-layer-btn")
                    )
                )
                publish_layer_btn.click()
            except TimeoutException:
                try:
                    btn = driver.find_element(
                        By.XPATH,
                        "//button[contains(text(), '완료') or contains(text(), '발행')]"
                    )
                    btn.click()
                except Exception as e:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        message=f"완료 버튼을 찾을 수 없습니다: {e}",
                    )

            random_delay(2.0, 3.0)

            # 7. 공개/비공개 설정 (라디오 버튼)
            # 기본값이 비공개(open0)이므로 공개(open20)로 전환
            is_private = content.visibility == "private"
            target_radio_id = "open0" if is_private else "open20"
            try:
                label = driver.find_element(
                    By.CSS_SELECTOR, f"label[for='{target_radio_id}']"
                )
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'})", label
                )
                random_delay(0.3, 0.5)
                # ActionChains로 물리적 클릭 (React 상태 변경 위해 필수)
                ActionChains(driver).move_to_element(label).click().perform()
                random_delay(0.5, 1.0)
            except Exception as e:
                logger.warning("[Tistory] 공개 설정 라디오 클릭 실패: %s", e)

            # 8. 발행 버튼 (publish-btn) 클릭
            try:
                publish_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button#publish-btn")
                    )
                )
                driver.execute_script("arguments[0].click()", publish_btn)
            except TimeoutException:
                try:
                    btn = driver.find_element(
                        By.XPATH,
                        "//button[contains(text(), '발행') or contains(text(), '저장')]"
                    )
                    driver.execute_script("arguments[0].click()", btn)
                except Exception as e:
                    return PublishResult(
                        success=False,
                        platform=self.platform,
                        message=f"발행 버튼을 찾을 수 없습니다: {e}",
                    )

            random_delay(5.0, 8.0)

            # 9. 결과 확인
            current_url = driver.current_url
            blog_domain = f"{self.blog_name}.tistory.com"

            if blog_domain in current_url and "manage/newpost" not in current_url:
                post_id = current_url.rstrip("/").split("/")[-1]
                logger.info("[Tistory] 글 발행 성공: %s", current_url)
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    post_id=post_id,
                    post_url=current_url,
                    message="Tistory 글 발행 완료",
                )

            # manage/posts로 리다이렉트된 경우 — 블로그 메인에서 최신 글 확인
            if "manage" in current_url:
                try:
                    driver.get(f"https://{self.blog_name}.tistory.com/")
                    random_delay(2.0, 3.0)
                    # 제목 텍스트로 최신 글 찾기
                    links = driver.find_elements(By.CSS_SELECTOR, "a")
                    for link in links:
                        if content.title[:10] in (link.text or ""):
                            post_url = link.get_attribute("href") or ""
                            if post_url and blog_domain in post_url:
                                post_id = post_url.rstrip("/").split("/")[-1]
                                logger.info("[Tistory] 글 발행 성공 (목록 확인): %s", post_url)
                                return PublishResult(
                                    success=True,
                                    platform=self.platform,
                                    post_id=post_id,
                                    post_url=post_url,
                                    message="Tistory 글 발행 완료",
                                )
                except Exception:
                    pass

                # 제목 매칭 실패해도 manage/posts로 갔으면 성공으로 간주
                logger.info("[Tistory] 글 발행 완료 (manage/posts 리다이렉트)")
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    post_id="",
                    post_url=f"https://{self.blog_name}.tistory.com/",
                    message="Tistory 글 발행 완료 (글 URL 확인 필요)",
                )

            return PublishResult(
                success=False,
                platform=self.platform,
                message=f"발행 후 URL 확인 실패. 현재 URL: {current_url}",
            )

        finally:
            browser.quit()

    def _login(self, browser: SNSBrowserManager) -> bool:
        """카카오 로그인. 쿠키 우선, 실패 시 credential 로그인."""
        driver = browser.driver

        # 쿠키 먼저 시도
        driver.get(f"https://{self.blog_name}.tistory.com/")
        random_delay(1.0, 2.0)
        if browser.load_cookies("kakao"):
            driver.refresh()
            random_delay(2.0, 3.0)
            if self._is_logged_in(driver):
                logger.info("[Tistory] 쿠키 로그인 성공")
                return True

        # 카카오 계정으로 로그인
        try:
            login_url = (
                f"{KAKAO_LOGIN_URL}"
                f"?continue=https://{self.blog_name}.tistory.com/manage"
            )
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

            # 카카오톡 인증 대기 (최초 로그인 시)
            if "accounts.kakao.com" in driver.current_url:
                logger.warning("[Tistory] 카카오톡 인증 대기 중 (60초)...")
                for _ in range(12):
                    time.sleep(5)
                    if "accounts.kakao.com" not in driver.current_url:
                        break

            # 로그인 확인
            driver.get(f"https://{self.blog_name}.tistory.com/manage")
            random_delay(2.0, 3.0)

            if self._is_logged_in(driver):
                browser.save_cookies("kakao")
                logger.info("[Tistory] 로그인 성공")
                return True

            logger.error("[Tistory] 로그인 실패")
            return False

        except Exception as e:
            logger.error("[Tistory] 로그인 예외: %s", e)
            return False

    def _is_logged_in(self, driver: Any) -> bool:
        try:
            page = driver.page_source
            return (
                "manage" in driver.current_url
                or "로그아웃" in page
                or "logout" in page.lower()
                or "tistory.com/manage" in driver.current_url
            )
        except Exception:
            return False

    def _set_tags(self, driver: Any, tags: list[str]) -> None:
        try:
            tag_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "input#tagText, "
                     "input.tag-input, "
                     "input[placeholder*='태그']")
                )
            )
            for tag in tags:
                tag_input.send_keys(tag)
                tag_input.send_keys(Keys.ENTER)
                random_delay(0.2, 0.4)
        except TimeoutException:
            logger.warning("[Tistory] 태그 입력 영역을 찾을 수 없습니다.")

    async def delete(self, post_id: str) -> bool:
        logger.warning("[Tistory] Selenium 기반 삭제는 현재 미지원입니다.")
        return False
