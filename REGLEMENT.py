import os
import json
import re
import time
from datetime import datetime
from tqdm import tqdm  # 导入tqdm库用于进度条显示
import unicodedata  # 用于处理Unicode字符规范化
import tiktoken
from collections import Counter

VALID_ZONE_RE = re.compile(r"^(?:\d?AU[A-Za-z0-9]?|[UAN][A-Za-z0-9]?)$", re.IGNORECASE)

try:
    import openai
    openai_available = True
    # 设置OpenAI API密钥（请替换为你自己的密钥）
    openai.api_key = "sk-proj-ll6oNC0m5tsykB24YExZT3BlbkFJDyMq9T2fbyliv2AtOxMs"
except ImportError:
    print("警告: 未找到openai模块，将使用正则表达式方法")
    openai_available = False

# —— 模型 & 最大输入 tokens（留 ~20% 生成空间） ——
MODEL = "gpt-4o-mini"
MAX_INPUT_TOKENS = 13000
enc = tiktoken.encoding_for_model(MODEL)


def find_zone_section(obj, zone_code):
    """递归在 JSON 中找到以 zone_code 为键的子 dict"""
    if isinstance(obj, dict):
        if zone_code in obj:
            return obj[zone_code]
        for v in obj.values():
            section = find_zone_section(v, zone_code)
            if section:
                return section
    elif isinstance(obj, list):
        for item in obj:
            section = find_zone_section(item, zone_code)
            if section:
                return section
    return None

def split_into_chunks(text: str) -> list[str]:
    token_ids = enc.encode(text)
    return [enc.decode(token_ids[i:i+MAX_INPUT_TOKENS])
            for i in range(0, len(token_ids), MAX_INPUT_TOKENS)]

def normalize_french_text(text):
    """
    规范化法语文本，处理特殊字符和重音符号
    """
    text = unicodedata.normalize('NFC', text)
    unicode_mappings = {
        "\\u00e0": "à", "\\u00e1": "á", "\\u00e2": "â", "\\u00e3": "ã",
        "\\u00e4": "ä", "\\u00e7": "ç", "\\u00e8": "è", "\\u00e9": "é",
        "\\u00ea": "ê", "\\u00eb": "ë", "\\u00ee": "î", "\\u00ef": "ï",
        "\\u00f4": "ô", "\\u00f9": "ù", "\\u00fb": "û", "\\u00fc": "ü",
        "\\u0153": "œ", "\\u00ab": "«", "\\u00bb": "»", "\\u2019": "'",
        "\\u2013": "-", "\\u2014": "—", "\\u00a0": " "
    }
    for esc, ch in unicode_mappings.items():
        text = text.replace(esc, ch)
    text = text.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def extract_with_openai_retry(text, max_retries=3,max_tokens=16384):
    """带重试机制的OpenAI API调用"""
    if not openai_available:
        return {"max_height": None, "max_coverage": None, "setback_distance": None}
    
    wait_time = 2  # 初始等待时间（秒）
    for attempt in range(max_retries):
        try:
            prompt = f"""Extraire les informations suivantes d'un règlement d'urbanisme français:
1. Hauteur maximale des bâtiments (max_height)
2. Emprise au sol maximale (max_coverage) 
3. Distance minimale de retrait/recul (setback_distance)

Texte du règlement:
{text[:4000]}

Répondre UNIQUEMENT au format JSON:
{{
  "max_height": "valeur avec unité ou null si non trouvé",
  "max_coverage": "valeur avec unité ou null si non trouvé",
  "setback_distance": "valeur avec unité ou null si non trouvé"
}}

Notes:
- Pour la hauteur, chercher des termes comme: "hauteur maximale", "hauteur maximum", "hauteur ne dépassant pas", etc.
- Pour l'emprise au sol, chercher: "emprise au sol", "coefficient d'emprise", "CES", etc.
- Pour le retrait, chercher: "recul", "retrait", "distance minimale", "marge de recul", etc.
"""
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Vous êtes un assistant spécialisé dans l'extraction d'informations à partir de documents d'urbanisme français. Vous devez extraire précisément les valeurs demandées sans ajouter d'informations supplémentaires."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=16384,
            )
            
            result_text = response.choices[0].message.content
            match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if match:
                result_json = json.loads(match.group(0))
                return result_json
            else:
                print(f"无法从API响应中提取JSON: {result_text}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return {
                    "max_height": None,
                    "max_coverage": None,
                    "setback_distance": None,
                }
        except Exception as e:
            error_msg = str(e).lower()
            if "rate limit" in error_msg and attempt < max_retries - 1:
                wait_time_match = re.search(r"try again in (\d+\.\d+)s", error_msg)
                wait_time = float(wait_time_match.group(1)) if wait_time_match else (2 ** (attempt + 1))
                print(f"OpenAI API速率限制，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time + 1)
            else:
                print(f"OpenAI API调用出错: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** (attempt + 1))
                else:
                    return {
                        "max_height": None,
                        "max_coverage": None,
                        "setback_distance": None,
                    }
    return {"max_height": None, "max_coverage": None, "setback_distance": None}

def extract_libzone_with_llm(text, libzone_list):
    """
    利用 LLM 直接提取 libzone 和 typezone。
    要求：
      1. libzone 必须是下列允许的代号之一：libzone_list 中的代号；
      2. 如果未匹配，返回 null；
      3. typezone 根据 libzone 特征确定：
           - 全数字 -> "numeric"
           - 同时包含数字和字母 -> "alphanumeric"
           - 仅字母 -> "string"
           - 未识别 -> "unknown"
    输出 JSON 格式：{"libzone": <代号或 null>, "typezone": <...>}
    """
    allowed_codes = ", ".join(sorted(list(libzone_list)))
    prompt = f"""
你是一名城市规划文档信息提取专家。请从以下文本中提取出 "libzone" 和 "typezone"。
要求：
1. "libzone" 必须是下列允许的代号之一：{allowed_codes}。
2. 如果文本中找不到匹配的 libzone，则返回 null。
3. "typezone" 根据 libzone 的特征确定：
   - 如果 libzone 只包含数字，则 typezone 为 "numeric"；
   - 如果 libzone 同时包含数字和字母，则 typezone 为 "alphanumeric"；
   - 如果 libzone 只包含字母，则 typezone 为 "string"；
   - 如果没有识别到 libzone，则 typezone 为 "unknown"。
请严格按照如下 JSON 格式输出结果，不要添加其他任何文字：
{{
  "libzone": "代号或 null",
  "typezone": "numeric 或 alphanumeric 或 string 或 unknown"
}}

以下是部分文本（仅截取前3000字符）：
{text[:3000]}
"""
    result = extract_with_openai_retry(prompt, max_tokens=300)
    if result and isinstance(result, dict):
        return result.get("libzone"), result.get("typezone")
    return None, "unknown"

def extract_with_regex(text):
    """增强的正则表达式函数，专为法语城市规划文档设计，返回规则值"""
    results = {
        "max_height": None,
        "max_coverage": None,
        "setback_distance": None,
    }
    
    height_patterns = [
        r"hauteur (maximale?|maximum)[^0-9]*?(\d+[.,]?\d*)\s*m",
        r"hauteur[^0-9]*?ne (doit|peut|pourra)[^0-9]*?d[ée]passer[^0-9]*?(\d+[.,]?\d*)\s*m",
        r"la hauteur des constructions ne peut exc[ée]der\s+(\d+[.,]?\d*)\s*m",
        r"hauteur est limit[ée]e [àa]\s+(\d+[.,]?\d*)\s*m",
        r"hauteur[^0-9]*?(\d+[.,]?\d*)\s*m[èe]tres",
        r"hauteur[^0-9]*?plafonn[ée]e [àa]\s+(\d+[.,]?\d*)\s*m",
        r"hauteur[^:;,]*?:[ \t]*(\d+[.,]?\d*)\s*m",
    ]
    
    coverage_patterns = [
        r"emprise au sol[^0-9]*?(\d+[.,]?\d*)\s*%",
        r"emprise au sol[^0-9]*?(\d+[.,]?\d*)[^%]*?pourcent",
        r"coefficient d'emprise au sol[^0-9]*?(\d+[.,]?\d*)",
        r"l'emprise au sol[^0-9]*?ne pourra exc[ée]der\s+(\d+[.,]?\d*)\s*%",
        r"CES[^0-9]*?(\d+[.,]?\d*)",
        r"coefficient d'emprise[^0-9]*?(\d+[.,]?\d*)",
        r"emprise[^:;,]*?:[ \t]*(\d+[.,]?\d*)\s*%",
    ]
    
    setback_patterns = [
        r"recul\s+[^0-9]*?(\d+[.,]?\d*)\s*m",
        r"retrait\s+[^0-9]*?(\d+[.,]?\d*)\s*m",
        r"distance\s+[^0-9]*?(\d+[.,]?\d*)\s*m",
        r"implant[ée]e avec un retrait minimum de\s+(\d+[.,]?\d*)\s*m",
        r"recul minimum[^0-9]*?(\d+[.,]?\d*)\s*m",
        r"marge de recul[^0-9]*?(\d+[.,]?\d*)\s*m",
        r"retrait[^:;,]*?:[ \t]*(\d+[.,]?\d*)\s*m",
    ]
    
    for pattern in height_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            group_idx = 1 if len(match.groups()) == 1 else 2
            value = match.group(group_idx).replace(",", ".")
            try:
                num_value = float(value)
                results["max_height"] = f"{int(num_value) if num_value == int(num_value) else round(num_value,1)} m"
            except:
                results["max_height"] = f"{value} m"
            break

    for pattern in coverage_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).replace(",", ".")
            try:
                num_value = float(value)
                results["max_coverage"] = f"{int(num_value) if num_value == int(num_value) else round(num_value,1)}%"
            except:
                results["max_coverage"] = f"{value}%"
            break

    for pattern in setback_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).replace(",", ".")
            try:
                num_value = float(value)
                results["setback_distance"] = f"{int(num_value) if num_value == int(num_value) else round(num_value,1)} m"
            except:
                results["setback_distance"] = f"{value} m"
            break
    
    return results

def extract_text(obj):
    """递归提取 JSON 中所有文本内容"""
    text_content = ""
    if isinstance(obj, str):
        return obj
    elif isinstance(obj, dict):
        for value in obj.values():
            text_content += " " + extract_text(value)
    elif isinstance(obj, list):
        for item in obj:
            text_content += " " + extract_text(item)
    return text_content



def extract_zone(text: str, filename: str, libzone_list: set):
    pattern = re.compile(r"Zone\s*([A-Za-z0-9]+)", re.IGNORECASE)
    match = pattern.search(text)
    zone_code = match.group(1).upper() if match else None

    # 如果不符合合法格式，就视为无效
    if zone_code and not VALID_ZONE_RE.match(zone_code):
        zone_code = None

    if zone_code:
        libzone_extracted = zone_code
    else:
        libzone_extracted, _ = extract_libzone_with_llm(text, libzone_list)

    if libzone_extracted:
        if libzone_extracted.isdigit():
            typezone = "numeric"
        elif any(c.isdigit() for c in libzone_extracted):
            typezone = "alphanumeric"
        else:
            typezone = "string"
    else:
        typezone = "unknown"

    return zone_code, libzone_extracted, typezone
def extract_insee(text, filename, json_obj=None):
    m = re.match(r"^(\d{5}|\d{9})", filename)
    if m:
        return m.group(1)
    return ""

def process_json_files():
    folder_path = input("请输入包含 JSON 文件的文件夹路径: ").strip()
    if folder_path and not folder_path.endswith(os.sep):
        folder_path += os.sep
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"指定的文件夹不存在: {folder_path}")

    output_json_path = input("请输入输出 JSON 文件的路径（例如 output.json）: ").strip()
    if not output_json_path.lower().endswith(".json"):
        output_json_path += ".json"

    json_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".json")]
    print(f"共找到 {len(json_files)} 个JSON文件待处理")

    # 读取 libzone.json，获取所有允许的代号
    try:
        with open("libell/libzone.json", "r", encoding="utf-8") as f:
            libzone_data = json.load(f)
        libzone_list = set(libzone_data.get("libelle", []))
    except Exception as e:
        print(f"加载 libzone.json 出错: {e}")
        libzone_list = set()

    results = {}
    missing_insee_count = 0
    success_logs = []
    failure_logs = []
    api_usage_count = 0
    max_api_calls = 50

    recognized_libzone_count = 0

    update_date = datetime.now().strftime("%Y-%m-%d")
    default_source = "Local Urban Plan"

    for filename in tqdm(json_files, desc="处理进度", unit="文件"):
        file_path = os.path.join(folder_path, filename)
        try:
            data = json.load(open(file_path, encoding="utf-8"))
        except Exception as e:
            failure_logs.append((filename, f"JSON解析错误: {e}"))
            continue

        raw_text = extract_text(data)
        if not raw_text:
            failure_logs.append((filename, "未找到任何文本内容"))
            continue

        cleaned_text = normalize_french_text(raw_text)
        matches = re.findall(r"Zone\s*([A-Za-z0-9]+)", cleaned_text, re.IGNORECASE)
        valid = [z.upper() for z in matches if VALID_ZONE_RE.match(z) and len(z)>=2]
        filtered = [z for z in valid if z in libzone_list]
        #print(f"[DEBUG] {filename} 有效候选: {valid}")
        #print(f"[DEBUG] {filename} 最终过滤: {filtered}")

       
        zone_code = Counter(filtered).most_common(1)[0][0] if filtered else None
       
       
        def extract_all_zone_codes(text: str, libzone_list: set) -> list[str]:
            matches = re.findall(r"Zone\s*([A-Za-z0-9]+)", text, re.IGNORECASE)
            valid = [m.upper() for m in matches if VALID_ZONE_RE.match(m)]
            filtered = [z for z in valid if z in libzone_list]
            return sorted(set(filtered))
        # 使用改进后的 extract_zone 函数：先用正则，如果不行则调用 LLM
        insee = extract_insee(cleaned_text, filename, data)

        if not insee:
            missing_insee_count += 1
            failure_logs.append((filename, "未提取到 INSEE"))
            continue

        regex_results = extract_with_regex(cleaned_text.lower())
        max_height = regex_results.get("max_height")
        max_coverage = regex_results.get("max_coverage")
        setback_distance = regex_results.get("setback_distance")

        zone_codes = extract_all_zone_codes(cleaned_text, libzone_list)
        libzone_extracted = zone_code  
      
        zone_codes = data.get("typezone", [])

        for zone_code in zone_codes:
            libzone = zone_code
            typezone = zone_code  # typezone 就等于 zone_code

            # 直接取 JSON 中同名 key 下的规则
            zone_rules = data.get(zone_code, {})

            output_obj = {
                "zone": zone_code,
                "libzone": libzone,
                "typezone": typezone,
                "insee": insee,
                "rules": {
                    "max_height": zone_rules.get("max_height", ""),
                    "max_coverage": zone_rules.get("max_coverage", ""),
                    "setback_distance": zone_rules.get("setback_distance", ""),
                },
                "update_date": update_date,
                "source": default_source,
                "source_file": filename,
            }
            results.setdefault(insee, []).append(output_obj)
        
       

        missing_fields = any(not val for val in [max_height, max_coverage, setback_distance])
        if openai_available and api_usage_count < max_api_calls and missing_fields:
            chunks = split_into_chunks(cleaned_text)
            llm_results = {"max_height": None, "max_coverage": None, "setback_distance": None}
            for chunk in chunks:
                part = extract_with_openai_retry(chunk)
                api_usage_count += 1
                if part and isinstance(part, dict):
                    for key in llm_results:
                        if not llm_results[key] and part.get(key):
                            llm_results[key] = part[key]
                if all(llm_results.values()):
                    break

            if not max_height and llm_results.get("max_height"):
                max_height = llm_results["max_height"]
            if not max_coverage and llm_results.get("max_coverage"):
                max_coverage = llm_results["max_coverage"]
            if not setback_distance and llm_results.get("setback_distance"):
                setback_distance = llm_results["setback_distance"]

        max_height = max_height or ""
        max_coverage = max_coverage or ""
        setback_distance = setback_distance or ""

        if libzone_extracted:
            recognized_libzone_count += 1

        output_obj = {
            "zone": zone_code,
            "libzone": libzone_extracted,
            "typezone": typezone,
            "insee": insee,
            "rules": {
                "max_height": max_height,
                "max_coverage": max_coverage,
                "setback_distance": setback_distance,
            },
            "update_date": update_date,
            "source": default_source,
            "source_file": filename,
        }
        results.setdefault(insee, []).append(output_obj)

        if max_height and max_coverage and setback_distance:
            success_logs.append(filename)
        else:
            missing_list = []
            if not max_height:
                missing_list.append("max_height")
            if not max_coverage:
                missing_list.append("max_coverage")
            if not setback_distance:
                missing_list.append("setback_distance")
            failure_logs.append((filename, f"缺少字段: {', '.join(missing_list)}"))

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "total_files": len(json_files),
                "success_files": len(success_logs),
                "incomplete_files": len(failure_logs),
                "missing_insee": missing_insee_count,
                "api_calls": api_usage_count,
                "recognized_libzone_count": recognized_libzone_count,
                "processed_date": update_date,
            },
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"处理完成！结果已保存至: {output_json_path}")
    print(f"成功解析的文件数: {len(success_logs)}")
    print(f"未完全解析的文件数: {len(failure_logs)}")
    print(f"未提取到 INSEE 的文件数: {missing_insee_count}")
    if openai_available:
        print(f"API调用次数: {api_usage_count}")
    print(f"成功识别到 libzone 的文件数: {recognized_libzone_count}")

if __name__ == "__main__":
    try:
        process_json_files()
    except Exception as e:
        print(f"程序执行出错: {e}")
