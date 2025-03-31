from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import BackgroundTasks
import os, uvicorn
import downloader
import matcher
import geopandas as gpd

app = FastAPI()

# Monter le répertoire des fichiers statiques (utilisé pour map.js et le fichier GeoJSON de sortie)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/output", StaticFiles(directory="output"), name="output")

templates = Jinja2Templates(directory="templates")

DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
if not os.path.exists("output"):
    os.makedirs("output")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/process", response_class=HTMLResponse)
async def process_insee(request: Request, insee: str = Form(...)):
    if not insee.isdigit() and (len(insee) != 5 or len(insee) != 9):
        raise HTTPException(status_code=400, detail="Veuillez saisir un code INSEE correct (5 chiffres) ou un code SIREN (9 chiffres)")
    
    # Vérifier si les données de la commune existent déjà, sinon télécharger et décompresser
    if not os.path.exists(f"{DATA_DIR}\\PLU_{insee}"):
        os.makedirs(f"{DATA_DIR}\\PLU_{insee}")
        data_folder = os.path.join(DATA_DIR, f"PLU_{insee}")
        try:
            data_folder = downloader.download_data(insee)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        data_folder = os.path.join(DATA_DIR, f"PLU_{insee}")
   
    # Supposons que zonage.shp se trouve dans data/PLU_{insee}/DOC_URBA/zonage.shp
    zonage_path = os.path.join(data_folder, "DOC_URBA", "zonage.shp")
    if not os.path.exists(zonage_path):
        raise HTTPException(status_code=404, detail=f"Le fichier zonage.shp n'a pas été trouvé dans les données pour le code INSEE {insee}.")
    
    # Charger zonage.shp
    try:
        gdf = gpd.read_file(zonage_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du chargement de zonage.shp : {e}")
    
    # Appeler le module matcher, pour associer les règles au GeoDataFrame
    gdf_matched = matcher.match_zoning(gdf, insee)
    gdf_matched = gdf_matched.to_crs(epsg=4326)
    
    # Enregistrer le résultat en GeoJSON dans le dossier output
    output_geojson = os.path.join("output", f"{insee}.geojson")
    try:
        gdf_matched.to_file(output_geojson, driver="GeoJSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'enregistrement du GeoJSON : {e}")
    
    # Obtenir simultanément tous les détails des règles de la commune actuelle pour l'affichage sur le frontend
    rules_details = matcher.get_rules_for_insee(insee)
    
    return templates.TemplateResponse("result.html", {
        "request": request,
        "insee": insee,
        "geojson_path": f"/output/{insee}.geojson",
        "rules": rules_details
    })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
