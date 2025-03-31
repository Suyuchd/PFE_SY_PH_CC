import json
import os
import pandas as pd

RULES_FILE = "rules.json"

def load_rules():
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Fusionner toutes les listes de règles associées aux codes INSEE dans un grand tableau
    all_rules = [record for rules in data["results"].values() for record in rules]
    df = pd.DataFrame(all_rules)
    return df

def get_rules_for_insee(insee_code: str):
    """
    Retourner tous les enregistrements dans rules.json dont le source_file commence par insee_code, pour l'affichage sur le frontend.
    """
    df = load_rules()
    df_insee = df[df["source_file"].str.startswith(insee_code)]
    # Si besoin de simplifier les données des règles, cela peut être fait ici, par exemple :
    # df_insee["max_height"] = df_insee["rules"].apply(lambda r: r.get("max_height", ""))
    # df_insee["max_coverage"] = df_insee["rules"].apply(lambda r: r.get("max_coverage", ""))
    # df_insee["setback_distance"] = df_insee["rules"].apply(lambda r: r.get("setback_distance", ""))
    return df_insee.to_dict(orient="records")

def match_zoning(gdf, insee_code: str):
    """
    Basé sur le champ "IDZONE" dans gdf (chargé depuis zonage.shp), comparer avec les enregistrements de rules.json dont le nom commence par insee_code, et assigner les règles correspondantes à chaque zone.
    """
    df_rules = load_rules()
    df_insee = df_rules[df_rules["source_file"].str.startswith(insee_code)]
    
    # Construire une correspondance : zone_code -> dictionnaire de règles (prendre le premier enregistrement)
    rule_map = {}
    for _, row in df_insee.iterrows():
        zone_code = row["libzone"].strip().upper()
        if zone_code not in rule_map:
            # Note : ici, row["rules"] est un dictionnaire, utilisez directement .get pour accéder aux champs internes
            rule_map[zone_code] = {
                "max_height": row["rules"].get("max_height") if isinstance(row["rules"], dict) else "",
                "max_coverage": row["rules"].get("max_coverage") if isinstance(row["rules"], dict) else "",
                "setback_distance": row["rules"].get("setback_distance") if isinstance(row["rules"], dict) else ""
            }
    
    def assign_rule(row):
        zone_type = row.get("LIBELLE", "").strip().upper()
        # 先尝试精确匹配
        if zone_type in rule_map:
            selected_rule = rule_map[zone_type]
        else:
            # 模糊匹配：在 rule_map 的键中查找以 zone_type 开头的候选项
            candidates = [key for key in rule_map.keys() if zone_type.startswith(key)]
            if candidates:
                # 选择匹配字符数最长的键
                best_key = max(candidates, key=len)
                selected_rule = rule_map[best_key]
            else:
                selected_rule = {"max_height": "", "max_coverage": "", "setback_distance": ""}
        row["max_height"] = selected_rule["max_height"]
        row["max_coverage"] = selected_rule["max_coverage"]
        row["setback_distance"] = selected_rule["setback_distance"]
        return row

    gdf = gdf.apply(assign_rule, axis=1)
    return gdf
