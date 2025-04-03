import os
import glob
import re

# -----------------------------
# 文件导入部分
# -----------------------------
folder_path=""
def load_ocr_files_from_folder(folder_path, file_extension="txt"):
    """
    从指定文件夹中批量导入OCR文本文件。
    参数：
      folder_path：OCR文件所在的文件夹路径
      file_extension：文件扩展名，默认为txt
    返回：
      一个字典，键为文件路径，值为文件内容
    """
    pattern = os.path.join(folder_path, f'*.{file_extension}')
    file_paths = glob.glob(pattern)
    
    files_data = {}
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            files_data[file_path] = content
            print(f"成功加载：{file_path}")
        except Exception as e:
            print(f"读取文件 {file_path} 时出错：{e}")
    return files_data

def load_ocr_file(file_path):
    """
    从单个OCR文件中导入文本数据。
    参数：
      file_path：OCR文件的完整路径
    返回：
      文件内容字符串
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"成功加载：{file_path}")
        return content
    except Exception as e:
        print(f"读取文件 {file_path} 时出错：{e}")
        return None

# -----------------------------
# 文本预处理部分
# -----------------------------
def clean_text(text):
    """
    清洗OCR文本：
      - 替换换行符为空格
      - 合并多个连续空格
      - 去除首尾空白字符
    """
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# -----------------------------
# 建立规则模板并抽取信息
# -----------------------------
def extract_rules(text):
    """
    利用正则表达式从文本中抽取规则信息。
    针对以下规则：
      - Hauteur maximale：建筑最大高度（单位：m）
      - Surface maximale au sol：最大地面面积（单位：m²）
      - Recul par rapport à la rue：与道路的最小距离（单位：m）
    """
    patterns = {
        "hauteur_maximale": r"Hauteur maximale\s*[:：]\s*([\d,\.]+)\s*m",
        "surface_maximale": r"Surface maximale(?: au sol)?\s*[:：]\s*([\d,\.]+)\s*m²",
        "recul": r"Recul(?: par rapport à la rue)?\s*[:：]\s*([\d,\.]+)\s*m"
    }
    
    extracted = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # 将数字中的逗号转换为点，便于转换为 float 类型
            value_str = match.group(1).replace(',', '.')
            extracted[key] = float(value_str)
        else:
            extracted[key] = None
    return extracted

# -----------------------------
# 主函数示例
# -----------------------------
if __name__ == "__main__":
    # 示例1：从文件夹批量加载OCR文件
    folder_path = "path/to/your/ocr_folder"  # 替换为实际文件夹路径
    ocr_files = load_ocr_files_from_folder(folder_path, file_extension="txt")
    print("批量加载的文件数量：", len(ocr_files))
    
    # 针对批量加载的每个文件，进行预处理和信息抽取
    for file_path, raw_text in ocr_files.items():
        cleaned = clean_text(raw_text)
        rules = extract_rules(cleaned)
        print(f"\n文件：{file_path}")
        print("抽取到的规则：", rules)
    
    # 示例2：加载单个OCR文件进行处理
    file_path = "path/to/your/ocr_file.txt"  # 替换为实际文件路径
    ocr_text = load_ocr_file(file_path)
    if ocr_text:
        cleaned_text = clean_text(ocr_text)
        extracted_rules = extract_rules(cleaned_text)
        print("\n单个文件处理结果：")
        print("抽取到的规则：", extracted_rules)
