// Tạo bản đồ tại Hà Nội.
const map = L.map('map').setView(
    [21.0285, 105.8542],
    13
);


L.tileLayer(
    'https://api.maptiler.com/maps/streets-v4/{z}/{x}/{y}.png?key=sNoxlO0FAES8rFELADJ5',
    {
        maxZoom: 20,

        attribution:
            '&copy; MapTiler &copy; OpenStreetMap contributors'
    }
).addTo(map);

let areas = [];
let draftPoints = [];
let selectedAreaId = null;
let isDrawing = false;
let mapBridge = null;

const savedAreaLayer = L.layerGroup().addTo(map);
const draftLayer = L.layerGroup().addTo(map);
const coverageLayer = L.layerGroup().addTo(map);

const countLabel = document.getElementById('area-count');
const areaList = document.getElementById('area-list');

function getSelectedArea() {
    return areas.find(area => area.id === selectedAreaId) || null;
}

function saveAreas() {
    if (!mapBridge) {
        showMessage('Chưa kết nối được với ứng dụng Python.');
        return;
    }
    mapBridge.save_search_areas(JSON.stringify({
        schema_version: 1,
        areas: areas
    }));
}

function showMessage(message) {
    document.getElementById('message').textContent = message;
}

function renderSavedAreas() {
    savedAreaLayer.clearLayers();
    coverageLayer.clearLayers();
    while (areaList.firstChild) {
        areaList.removeChild(areaList.firstChild);
    }

    if (areas.length === 0) {
        areaList.add(new Option('Chưa có khu vực', ''));
        selectedAreaId = null;
    } else {
        areas.forEach(area => {
            const option = new Option(area.name, area.id);
            areaList.add(option);

            const isSelected = area.id === selectedAreaId;
            const polygon = L.polygon(
                area.coordinates.map(point => [point.lat, point.lon]),
                {
                    color: isSelected ? '#1769aa' : '#718096',
                    fillColor: isSelected ? '#1769aa' : '#718096',
                    fillOpacity: isSelected ? 0.28 : 0.12,
                    weight: isSelected ? 3 : 2
                }
            ).bindTooltip(area.name).addTo(savedAreaLayer);

            polygon.on('click', event => {
                L.DomEvent.stopPropagation(event.originalEvent);
                if (!isDrawing) {
                    selectArea(area.id);
                }
            });
        });
        areaList.value = selectedAreaId || '';
    }

    const selectedArea = getSelectedArea();
    document.getElementById('area-count').textContent =
        `${areas.length} khu vực${selectedArea ? ` | ${selectedArea.coordinates.length} điểm` : ''}`;
    document.getElementById('area-name').value = selectedArea
        ? selectedArea.name
        : '';
    document.getElementById('coordinate-list').textContent = selectedArea
        ? JSON.stringify(selectedArea.coordinates, null, 2)
        : 'Chọn một khu vực để xem tọa độ.';
}

function renderDraft() {
    draftLayer.clearLayers();
    coverageLayer.clearLayers();

    draftPoints.forEach((point, index) => {
        L.marker([point.lat, point.lon])
            .bindTooltip(`Điểm ${index + 1} của polygon mới`)
            .addTo(draftLayer);
    });

    if (draftPoints.length >= 3) {
        L.polygon(
            draftPoints.map(point => [point.lat, point.lon]),
            { color: '#f28c28', fillOpacity: 0.2, dashArray: '6, 6' }
        ).addTo(draftLayer);
    } else if (draftPoints.length === 2) {
        L.polyline(
            draftPoints.map(point => [point.lat, point.lon]),
            { color: '#f28c28', dashArray: '6, 6' }
        ).addTo(draftLayer);
    }

    countLabel.textContent = isDrawing
        ? `${areas.length} khu vực đã lưu | ${draftPoints.length} điểm đang vẽ`
        : `${areas.length} khu vực`;
}

function selectArea(areaId) {
    selectedAreaId = areaId;
    renderSavedAreas();
    if (areaId) {
        showMessage(`Đang chọn ${getSelectedArea().name}.`);
    }
}

function startDrawing() {
    if (isDrawing && draftPoints.length > 0
            && !window.confirm('Bỏ polygon đang vẽ và bắt đầu polygon mới?')) {
        return;
    }
    isDrawing = true;
    draftPoints = [];
    renderDraft();
    showMessage('Click bản đồ để thêm điểm cho polygon mới.');
}

map.on('click', event => {
    if (!isDrawing) {
        return;
    }

    draftPoints.push({
        lat: Number(event.latlng.lat.toFixed(7)),
        lon: Number(event.latlng.lng.toFixed(7))
    });
    renderDraft();
});

document.getElementById('undo-point').addEventListener('click', () => {
    if (!isDrawing) {
        showMessage('Nhấn “Vẽ đa giác mới” trước khi thêm hoặc xóa điểm.');
        return;
    }
    draftPoints.pop();
    renderDraft();
});

document.getElementById('new-area').addEventListener('click', startDrawing);

document.getElementById('cancel-drawing').addEventListener('click', () => {
    draftPoints = [];
    isDrawing = false;
    renderDraft();
    renderSavedAreas();
    showMessage('Đã hủy polygon đang vẽ.');
});

document.getElementById('finish-area').addEventListener('click', () => {
    if (!isDrawing || draftPoints.length < 3) {
        showMessage('Vẽ ít nhất 3 điểm trước khi hoàn thành polygon.');
        return;
    }
    if (!mapBridge) {
        showMessage('Chưa kết nối được với ứng dụng Python.');
        return;
    }

    const nextNumber = areas.length + 1;
    const newArea = {
        id: `area-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
        name: `Khu vực ${nextNumber}`,
        coordinates: draftPoints
    };
    areas.push(newArea);
    selectedAreaId = newArea.id;
    draftPoints = [];
    isDrawing = false;
    renderDraft();
    renderSavedAreas();
    saveAreas();
});

areaList.addEventListener('change', () => {
    if (!isDrawing) {
        selectArea(areaList.value || null);
    }
});

document.getElementById('rename-area').addEventListener('click', () => {
    const selectedArea = getSelectedArea();
    const newName = document.getElementById('area-name').value.trim();
    if (!selectedArea) {
        showMessage('Hãy chọn polygon cần đổi tên.');
        return;
    }
    if (!newName) {
        showMessage('Tên polygon không được để trống.');
        return;
    }
    selectedArea.name = newName;
    renderSavedAreas();
    saveAreas();
});

document.getElementById('delete-area').addEventListener('click', () => {
    const selectedArea = getSelectedArea();
    if (!selectedArea) {
        showMessage('Hãy chọn polygon cần xóa.');
        return;
    }
    if (!window.confirm(`Xóa ${selectedArea.name}?`)) {
        return;
    }

    areas = areas.filter(area => area.id !== selectedAreaId);
    selectedAreaId = areas.length > 0 ? areas[0].id : null;
    renderSavedAreas();
    saveAreas();
});

document.getElementById('generate-path').addEventListener('click', () => {
    const selectedArea = getSelectedArea();
    if (!selectedArea) {
        showMessage('Hãy chọn một polygon trước khi tạo đường quét.');
        return;
    }
    if (!mapBridge) {
        showMessage('Chưa kết nối được với ứng dụng Python.');
        return;
    }

    const spacing = Number(document.getElementById('spacing').value);
    mapBridge.generate_coverage_path(
        JSON.stringify(selectedArea.coordinates), spacing
    );
});

new QWebChannel(qt.webChannelTransport, channel => {
    mapBridge = channel.objects.mapBridge;
    mapBridge.status_changed.connect(message => {
        showMessage(message);
    });
    mapBridge.search_areas_loaded.connect(documentJson => {
        const document = JSON.parse(documentJson);
        areas = document.areas;
        selectedAreaId = areas.length > 0 ? areas[0].id : null;
        renderSavedAreas();

        if (areas.length > 0) {
            const allCoordinates = areas.flatMap(area => area.coordinates);
            const bounds = L.latLngBounds(
                allCoordinates.map(point => [point.lat, point.lon])
            );
            map.fitBounds(bounds, { padding: [20, 20], maxZoom: 16 });
        }
    });
    mapBridge.search_areas_saved.connect(documentJson => {
        const document = JSON.parse(documentJson);
        areas = document.areas;
        renderSavedAreas();
    });
    mapBridge.coverage_path_ready.connect(pathJson => {
        const coveragePath = JSON.parse(pathJson);
        coverageLayer.clearLayers();

        coveragePath.segments.forEach(segment => {
            L.polyline(
                segment.map(point => [point.lat, point.lon]),
                { color: '#e53935', weight: 3 }
            ).addTo(coverageLayer);
        });
    });
    mapBridge.load_search_areas();
});
