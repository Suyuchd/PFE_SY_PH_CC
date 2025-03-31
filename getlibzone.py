import os
import json
from tqdm import tqdm  # 需要先安装 tqdm：pip install tqdm

# 设置包含 JSON 文件的文件夹路径
folder_path = 'json'
output_file = 'libzone.json'

# 用集合保存 libelle 和 typezone 的唯一值
libelle_set = set()
typezone_set = set()

# 获取所有 JSON 文件列表
json_files = [filename for filename in os.listdir(folder_path) if filename.endswith('.json')]

# 遍历所有文件，使用 tqdm 显示进度条
for filename in tqdm(json_files, desc="正在处理文件"):
    file_path = os.path.join(folder_path, filename)
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            features = data.get("features", [])
            for feature in features:
                properties = feature.get("properties", {})
                libelle = properties.get("libelle")
                typezone = properties.get("typezone")
                if libelle is not None:
                    libelle_set.add(libelle)
                if typezone is not None:
                    typezone_set.add(typezone)
        except json.JSONDecodeError as e:
            print(f"文件 {filename} 解析出错：{e}")

# 将集合转为列表（此处不排序，可按实际需要排序）
result = {
    "libelle": sorted(list(libelle_set)),
    "typezone": sorted(list(typezone_set))
}

# 将结果写入 JSON 文件
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=4)

print(f"输出文件已保存到 {output_file}")