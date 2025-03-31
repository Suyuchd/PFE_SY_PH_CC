function initMap(geojsonUrl) {
    var map = L.map('map').setView([46.8, 2.3], 6); // 法国范围
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    fetch(geojsonUrl)
      .then(response => response.json())
      .then(data => {
          const geojsonLayer = L.geoJSON(data, {
              style: function (feature) {
                  const zoneType = feature.properties.TYPEZONE;
                  let color = "#3388ff"; // 默认蓝色
                  if (zoneType === "A") color = "#FFA500"; // orange for agricultural
                  else if (zoneType === "N") color = "#228B22"; // green for natural
                  else if (zoneType === "U") color = "#8B0000"; // dark red for urban
                  return {
                      color: color,
                      fillColor: color,
                      fillOpacity: 0.3,
                      weight: 2
                  };
              },
              onEachFeature: function (feature, layer) {
                  const props = feature.properties;
                  const popupContent = `
                    <b>Zone:</b> ${props.LIBELLE || "未知"}<br>
                    <b>Type:</b> ${props.TYPEZONE || "?"}<br>
                    <b>Description:</b> ${props.LIBELONG || "无"}<br>
                    <b>Max Height:</b> ${props.max_height || "无"}<br>
                    <b>Max Coverage:</b> ${props.max_coverage || "无"}<br>
                    <b>Setback:</b> ${props.setback_distance || "无"}
                  `;
                  layer.bindPopup(popupContent);
              }
          }).addTo(map);

          // 如果你想缩放到区域范围，而不是整个法国，可以启用以下语句：
          // map.fitBounds(geojsonLayer.getBounds());
      })
      .catch(error => {
          console.error("Error loading GeoJSON:", error);
      });
}