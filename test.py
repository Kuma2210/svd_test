import os
import json
import base64
import uuid
import requests  # 我们现在只使用 requests 库
from tqdm import tqdm
import time

# --- 1. 配置您的火山引擎身份认证信息 ---
# 请替换为您的真实 AppID 和 Token
APPID = "YOUR_APPID"
TOKEN = "YOUR_TOKEN"

# --- 2. 配置输入和输出路径 ---
# 请替换为您的音频文件夹路径
AUDIO_FOLDER_PATH = "/path/to/your/audio/files"
# 请替换为您希望生成的 JSON 文件路径
OUTPUT_JSON_PATH = "/path/to/your/output/result.json"

# --- 3. 配置API信息 (请根据官方文档核对) ---
# 这是火山引擎SAMI（智能音频）服务的通用任务接口URL，大概率是这个
# 请务必在官网文档中确认此URL是否正确
VAD_API_URL = "https://vcloud.volcengineapi.com/sami/v1/task"


def detect_singing_with_requests(audio_path, app_id, token):
    """
    使用 requests 库直接调用火山引擎VAD API进行歌唱检测。

    Args:
        audio_path (str): 音频文件路径。
        app_id (str): 您的 AppID。
        token (str): 您的 Token。

    Returns:
        dict: 格式化后的分析结果，如果失败则返回 None。
    """
    try:
        # 1. 读取音频文件并进行Base64编码
        with open(audio_path, 'rb') as f:
            audio_data_base64 = base64.b64encode(f.read()).decode('utf-8')

        # 2. 构建请求头 (Header)
        # Token 通常放在 Authorization Header 中
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer; {token}"
        }

        # 3. 构建请求体 (Body)
        # 这是请求的核心，其结构必须严格符合火山引擎官方文档的要求。
        request_body = {
            "app": {
                "appid": app_id,
                # "token": token, # 有些接口也要求在Body中再传一次
            },
            "task": {
                "task_id": f"vad_singing_{uuid.uuid4()}", # 使用UUID确保每次请求的ID唯一
                "task_type": "vad",  # 任务类型：语音活动检测
                "config": {
                    "output_granularity": "second",  # 输出粒度：秒
                    "enable_singing_detection": True,  # **关键：启用歌唱检测**
                    "language": "zh"  # 根据您的音频语言设置 (中文普通话)
                }
            },
            "data": {
                "data_type": "base64",
                "content": audio_data_base64
            }
        }

        # 4. 发送POST请求
        # 设置一个合理的超时时间，例如60秒
        response = requests.post(VAD_API_URL, headers=headers, json=request_body, timeout=60)
        
        # 5. 处理响应
        if response.status_code == 200:
            response_json = response.json()
            # 根据火山引擎通用返回格式，检查业务状态码
            if response_json.get("status_code") == 0:  # 0 通常代表成功
                return parse_result(response_json.get('result', {}))
            else:
                error_msg = response_json.get('status_text', '未知错误')
                print(f"文件 '{os.path.basename(audio_path)}' API返回业务错误: {error_msg}")
                return None
        else:
            print(f"请求失败，文件: '{os.path.basename(audio_path)}', HTTP状态码: {response.status_code}, 响应: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"处理文件 '{os.path.basename(audio_path)}' 时发生网络错误: {e}")
        return None
    except Exception as e:
        print(f"处理文件 '{os.path.basename(audio_path)}' 时发生未知错误: {e}")
        return None


def parse_result(result_data):
    """
    解析API返回的JSON结果，格式化为我们需要的格式。
    注意：此解析逻辑基于对API返回格式的推测，您可能需要根据实际返回结果进行微调。
    """
    if not result_data:
        return None
        
    duration = int(round(result_data.get("duration", 0)))
    judge_list = [0] * duration
    
    for segment in result_data.get("segments", []):
        if segment.get("type") == "singing":
            start_sec = int(segment.get('start_time', 0))
            end_sec = int(segment.get('end_time', 0))
            for i in range(start_sec, min(end_sec, duration)):
                judge_list[i] = 1
                
    is_singing = any(j == 1 for j in judge_list)
    
    formatted_result = {
        "是否为唱歌": is_singing,
        "人声占比": result_data.get("voice_activity_ratio", 0.0),
        "置信度": result_data.get("confidence", 0.0),
        "judge": judge_list
    }
    return formatted_result


def main():
    """
    主函数，执行批量处理
    """
    if not os.path.isdir(AUDIO_FOLDER_PATH):
        print(f"错误：提供的路径 '{AUDIO_FOLDER_PATH}' 不是一个有效的文件夹。")
        return

    supported_extensions = ('.wav', '.mp3', '.pcm', '.m4a')
    audio_files = [f for f in os.listdir(AUDIO_FOLDER_PATH) if f.lower().endswith(supported_extensions)]
    
    if not audio_files:
        print(f"在文件夹 '{AUDIO_FOLDER_PATH}' 中没有找到支持的音频文件。")
        return

    print(f"找到 {len(audio_files)} 个音频文件。开始处理...")

    all_results = []
    for filename in tqdm(audio_files, desc="处理音频文件"):
        audio_path = os.path.join(AUDIO_FOLDER_PATH, filename)
        result = detect_singing_with_requests(audio_path, APPID, TOKEN)
        
        if result:
            final_output = {
                "audio_id": filename,
                **result
            }
            all_results.append(final_output)
        
        # 接口可能有频率限制，如有需要可以增加延时
        # time.sleep(0.5) # 暂停0.5秒

    try:
        with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=4)
        print(f"\n处理完成！结果已保存到: {OUTPUT_JSON_PATH}")
    except Exception as e:
        print(f"\n写入结果文件时发生错误: {e}")

if __name__ == '__main__':
    main()
