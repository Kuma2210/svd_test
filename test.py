import os
import json
import base64
import uuid
from tqdm import tqdm
from volcengine.auth.SignerV4 import SignerV4
from volcengine.common.Models import VpcInfo
from volcengine.models.vod.request.request_vod_pb2 import VodSubmitDirectEditTaskAsyncRequest
from volcengine.vod.VodService import VodService

# --- 配置您的火山引擎身份认证信息 ---
# 请替换为您的真实 AppID 和 Token
APPID = "YOUR_APPID"
TOKEN = "YOUR_TOKEN"
# 推荐使用火山引擎访问密钥（AK/SK）以获得更安全的认证方式
# 如果使用 AK/SK，请取消下面两行的注释并填入您的信息
# ACCESS_KEY = "YOUR_ACCESS_KEY"
# SECRET_KEY = "YOUR_SECRET_KEY"

# --- 配置输入和输出路径 ---
# 请替换为您的音频文件夹路径
AUDIO_FOLDER_PATH = "/path/to/your/audio/files"
# 请替换为您希望生成的 JSON 文件路径
OUTPUT_JSON_PATH = "/path/to/your/output/result.json"


class SingingVoiceDetector:
    """
    使用火山引擎VAD能力进行歌唱检测的类
    """

    def __init__(self, appid, token):
        """
        初始化客户端
        """
        if not appid or not token:
            raise ValueError("APPID 和 Token 不能为空！")
        
        # 初始化 VOD 服务。VAD能力通常集成在VOD(视频点播)或ASR(语音识别)服务下。
        # 这里我们使用通用的方式构建请求，因为VAD可能没有独立的离线批量处理SDK。
        # 我们将采用提交任务的方式进行。
        self.vod_service = VodService()
        # self.vod_service.set_ak(ACCESS_KEY) # 如果使用 AK/SK
        # self.vod_service.set_sk(SECRET_KEY) # 如果使用 AK/SK
        # 注意：截至目前，火山引擎的Python SDK可能没有直接暴露VAD的接口。
        # 因此，我们将模拟一个对API网关的HTTP POST请求。
        # 这是更通用和可靠的方式。
        self.api_url = "https://open.volcengineapi.com/?Action=SubmitDirectEditTaskAsync&Version=2020-08-01" # 这是一个示例URL，需要查阅最新文档确认
        self.service_name = "vod"
        self.region = "cn-north-1" # 根据您的服务区域调整

        # 实际调用的VAD接口信息 (需要根据最新文档确认)
        self.vad_api_url = "https://vcloud.volcengineapi.com/sami/v1/task" # SAMI (Smart Audio & Music Intelligence) 平台下的VAD接口
        self.auth_header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer; {token}" # Token认证方式
        }


    def detect_singing_in_file(self, audio_path):
        """
        对单个音频文件进行歌唱检测
        
        Args:
            audio_path (str): 音频文件路径

        Returns:
            dict: 包含分析结果的字典，如果失败则返回None
        """
        try:
            with open(audio_path, 'rb') as f:
                audio_data_base64 = base64.b64encode(f.read()).decode('utf-8')

            # 构建请求体 (Body)
            # 重要：请求体的具体格式需要严格参考火山引擎最新的SAMI VAD接口文档。
            # 以下是一个根据通用VAD功能推测的示例结构。
            request_body = {
                "app": {
                    "appid": APPID,
                    "token": TOKEN # 有些接口要求token在body和header中都存在
                },
                "task": {
                    "task_id": f"vad_singing_{uuid.uuid4()}",
                    "task_type": "vad", # 任务类型
                    "config": {
                        "output_granularity": "second", # 输出粒度为秒
                        "enable_singing_detection": True, # **启用歌唱检测的关键参数**
                        "language": "zh" # 根据音频语言设置
                    }
                },
                "data": {
                    "data_type": "base64",
                    "content": audio_data_base64
                }
            }
            
            # 使用requests库发送POST请求
            import requests
            response = requests.post(self.vad_api_url, headers=self.auth_header, json=request_body, timeout=60)
            
            if response.status_code == 200:
                response_json = response.json()
                # 检查返回结果中是否包含错误信息
                if response_json.get("status_code") == 0: # 假设 0 代表成功
                    return self._parse_result(response_json['result'])
                else:
                    print(f"文件 '{os.path.basename(audio_path)}' 分析失败: {response_json.get('status_text')}")
                    return None
            else:
                print(f"请求失败，文件: '{os.path.basename(audio_path)}', 状态码: {response.status_code}, 响应: {response.text}")
                return None

        except Exception as e:
            print(f"处理文件 '{os.path.basename(audio_path)}' 时发生错误: {e}")
            return None

    @staticmethod
    def _parse_result(result_data):
        """
        解析API返回的JSON结果，格式化为我们需要的格式。
        解析逻辑需要根据实际API返回的结构进行调整。
        """
        # 假设API返回结构如下:
        # {
        #   "overall_decision": "singing", // or "speech", "mixed"
        #   "confidence": 0.95,
        #   "voice_activity_ratio": 0.8,
        #   "segments": [
        #     {"start_time": 0.0, "end_time": 1.0, "type": "no_voice"},
        #     {"start_time": 1.0, "end_time": 2.0, "type": "singing"},
        #     {"start_time": 2.0, "end_time": 3.0, "type": "no_voice"},
        #     ...
        #   ],
        #   "duration": 30.5
        # }
        
        duration = int(round(result_data.get("duration", 0)))
        judge_list = [0] * duration
        
        for segment in result_data.get("segments", []):
            if segment.get("type") == "singing":
                start_sec = int(segment['start_time'])
                end_sec = int(segment['end_time'])
                for i in range(start_sec, min(end_sec, duration)):
                    judge_list[i] = 1
                    
        is_singing = result_data.get("overall_decision") == "singing" or any(j == 1 for j in judge_list)
        
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

    # 获取所有支持的音频文件
    supported_extensions = ('.wav', '.mp3', '.pcm', '.m4a')
    audio_files = [f for f in os.listdir(AUDIO_FOLDER_PATH) if f.lower().endswith(supported_extensions)]
    
    if not audio_files:
        print(f"在文件夹 '{AUDIO_FOLDER_PATH}' 中没有找到支持的音频文件。")
        return

    print(f"找到 {len(audio_files)} 个音频文件。开始处理...")

    detector = SingingVoiceDetector(APPID, TOKEN)
    all_results = []

    for filename in tqdm(audio_files, desc="处理音频文件"):
        audio_path = os.path.join(AUDIO_FOLDER_PATH, filename)
        result = detector.detect_singing_in_file(audio_path)
        
        if result:
            final_output = {
                "audio_id": filename,
                **result
            }
            all_results.append(final_output)

    # 将所有结果写入一个JSON文件
    try:
        with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=4)
        print(f"\n处理完成！结果已保存到: {OUTPUT_JSON_PATH}")
    except Exception as e:
        print(f"\n写入结果文件时发生错误: {e}")


if __name__ == '__main__':
    # --- 重要提示 ---
    # 在运行前，请仔细阅读代码开头的配置部分，并填入您的个人信息和路径。
    # 特别是 `SingingVoiceDetector` 类中的 `vad_api_url` 和请求体 `request_body`
    # 的结构，强烈建议您根据最新的火山引擎官方文档进行核对和修改，因为API细节可能会更新。
    main()
