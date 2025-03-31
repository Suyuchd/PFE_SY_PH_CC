import os
import requests
import zipfile
import shutil
from requests.adapters import HTTPAdapter, Retry
from tqdm import tqdm
import sys

if sys.platform.startswith("win"):
    # Forcer la réinitialisation de la sortie standard en UTF-8
    sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def download_data(insee_code: str) -> str:
    url = f"https://www.geoportail-urbanisme.gouv.fr/api/document/download-by-partition/DU_{insee_code}"
    _download_and_extract(url, insee_code)
    return os.path.join(DATA_DIR, f"PLU_{insee_code}")

def _download_and_extract(url, insee_code):
    zip_path = os.path.join(DATA_DIR, f"DU_{insee_code}.zip")
    extract_folder = os.path.join(DATA_DIR, f"DU_{insee_code}")

    session = requests.Session()
    session.mount("https://", HTTPAdapter(
        max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429,500,502,503,504])
    ))

    try:
        # —— Envoyer une requête HEAD pour obtenir la véritable adresse ZIP redirigée
        head = session.head(url, allow_redirects=True, timeout=10)
        download_url = head.url
        print(f"Adresse de téléchargement réelle : {download_url}")

        # —— Téléchargement en flux : délai de connexion de 10s + délai de lecture de 600s
        with session.get(download_url, stream=True, timeout=(10,600)) as resp:
            resp.raise_for_status()
            total_size = int(resp.headers.get("Content-Length", 0))
            with open(zip_path, "wb") as f, tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"Téléchargement de DU_{insee_code}.zip"
         ) as bar:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    bar.update(len(chunk))

        # —— Décompresser et traiter
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_folder)

        target_folder = os.path.join(DATA_DIR, f"PLU_{insee_code}", "DOC_URBA")
        os.makedirs(target_folder, exist_ok=True)

        found = False
        for root, _, files in os.walk(extract_folder):
            for fname in files:
                if fname.lower().endswith(".shp") and "zone" in fname.lower():
                    found = True
                    base = os.path.splitext(fname)[0]
                    for ext in [".shp", ".dbf", ".shx", ".prj", ".cpg"]:
                        src = os.path.join(root, base + ext)
                        if os.path.exists(src):
                            dst = os.path.join(target_folder, "zonage" + ext)
                            print(f"Déplacer {src} → {dst}")
                            shutil.move(src, dst)

        if not found:
            print("⚠️ Aucun fichier shapefile contenant 'zone' n'a été trouvé !")

        # Nettoyer
        os.remove(zip_path)
        shutil.rmtree(extract_folder)
        return target_folder

    except requests.exceptions.ReadTimeout:
        print("Délai d'attente dépassé lors du téléchargement, veuillez vérifier votre connexion ou réessayer plus tard")
    except Exception as e:
        print(f"Échec du traitement : {e}")

    if os.path.exists(zip_path):
        os.remove(zip_path)
    return None
