import json
import pickle
import zipfile
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_user_data(file_path):
    """JSONファイルからユーザーデータを読み込む"""
    with open(file_path, 'r') as file:
        return json.load(file)

def create_proxy_auth_extension(proxy_host, proxy_port, proxy_username, proxy_password, scheme='http', plugin_path=None):
    """
    プロキシ認証用のChrome拡張機能を作成する
    """
    if plugin_path is None:
        plugin_path = 'proxy_auth_plugin.zip'

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "%s",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (scheme, proxy_host, proxy_port, proxy_username, proxy_password)

    with zipfile.ZipFile(plugin_path, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    return plugin_path

def setup_driver(proxy):
    """Chromeドライバーを設定し、初期化する"""
    chrome_options = Options()
    
    if proxy:
        proxy_parts = proxy.split(':')
        if len(proxy_parts) == 4:
            proxy_host, proxy_port, proxy_username, proxy_password = proxy_parts
            plugin_path = create_proxy_auth_extension(
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                proxy_username=proxy_username,
                proxy_password=proxy_password
            )
            chrome_options.add_extension(plugin_path)
        else:
            chrome_options.add_argument(f'--proxy-server={proxy}')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def login_to_threads(driver, username, password):
    """Threadsにログインする"""
    driver.get("https://www.threads.net/login")
    
    # ユーザー名入力フィールドを待機し、入力
    username_field = WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'][class*='x1i10hfl'][class*='x1a2a7pz']"))
        )

    username_field.clear()
    username_field.send_keys(username)
    logging.info("ユーザー名を入力しました")
        
        # パスワード入力フィールドを見つけ、入力
    password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    password_field.clear()
    password_field.send_keys(password)
    logging.info("パスワードを入力しました")
        
        # 入力後、短い待機時間を設定
    time.sleep(2)
        
    # ログインボタンを見つけてクリック
    login_button_xpath = "//div[@role='button' and contains(@class, 'x1i10hfl') and contains(@class, 'x1qjc9v5')]//div[contains(text(), 'Log in') or contains(text(), 'ログイン')]"
    login_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, login_button_xpath))
    )
    driver.execute_script("arguments[0].click();", login_button)
    logging.info("ログインボタンをクリックしました")

    time.sleep(20)

    return check_login_status(driver)


# ログイン状態をチェックする関数
def check_login_status(driver, timeout=120):
    """
    'Post'または'投稿'要素の存在に基づいてログイン状態を確認する

    :param driver: WebDriverオブジェクト
    :param timeout: 要素を待機する最大時間（秒）
    :return: ログインしている場合はTrue、そうでない場合はFalse
    """
    logging.info("ログイン状態のチェックを開始します。")
    try:
        # 'Post'または'投稿'要素を探す
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, 
                "//div[contains(@class, 'xc26acl') and contains(@class, 'x6s0dn4') and contains(@class, 'x78zum5') and (contains(text(), 'Post') or contains(text(), '投稿'))]"
            ))
        )
        logging.info(f"'Post'または'投稿'要素が見つかりました。テキスト: '{element.text}'")
        logging.info("ログイン状態が確認されました。")
        return True
    except TimeoutException:
        logging.warning(f"'Post'または'投稿'要素が {timeout} 秒以内に見つかりませんでした。")
        logging.info("ログアウト状態であると判断します。")
        return False
    except NoSuchElementException:
        logging.warning("'Post'または'投稿'要素が存在しません。")
        logging.info("ログアウト状態であると判断します。")
        return False
    except Exception as e:
        logging.error(f"ログイン状態の確認中に予期せぬエラーが発生しました: {str(e)}")
        logging.info("ログアウト状態であると判断します。")
        return False
        


def save_session(driver, username):
    """セッション情報を保存する"""
    session = driver.get_cookies()
    with open(f'cookies_{username}.pkl', 'wb') as file:
        pickle.dump(session, file)
    logging.info(f"ユーザー {username} のセッション情報を保存しました。")

def main():
    user_data = load_user_data('user_data.json')
    
    for user in user_data:
        username = user['username']
        password = user['password']
        proxy = user['proxy']
        
        driver = setup_driver(proxy)
        
        try:
            if login_to_threads(driver, username, password):
                save_session(driver, username)
            else:
                logging.info(f"エラーです。")
        except Exception as e:
            logging.error(f"ユーザー {username} のログイン中にエラーが発生しました: {str(e)}")
            # コマンドプロンプトを開いたままにする
            input("処理が完了しました。Enterキーを押して終了してください...")
        finally:
            # コマンドプロンプトを開いたままにする
            input("処理が完了しました。Enterキーを押して終了してください...")

    # 一時的に作成した拡張機能ファイルを削除
    if os.path.exists('proxy_auth_plugin.zip'):
        os.remove('proxy_auth_plugin.zip')

if __name__ == "__main__":
    main()