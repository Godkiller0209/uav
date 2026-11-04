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

const points = [];
const markers = L.layerGroup().addTo(map);
const coverageLayer = L.layerGroup().addTo(map);
let areaShape = null;
let mapBridge = null;

const countLabel = document.getElementById('point-count');
const confirmButton = document.getElementById('confirm-area');

function updateArea() {
    markers.clearLayers();
    coverageLayer.clearLayers();

    points.forEach((point, index) => {
        L.marker([point.lat, point.lon])
            .bindTooltip(`Điểm ${index + 1}`)
            .addTo(markers);
    });

    if (areaShape) {
        map.removeLayer(areaShape);
        areaShape = null;
    }

    if (points.length >= 3) {
        areaShape = L.polygon(
            points.map(point => [point.lat, point.lon]),
            { color: '#1769aa', fillOpacity: 0.2 }
        ).addTo(map);
    } else if (points.length === 2) {
        areaShape = L.polyline(
            points.map(point => [point.lat, point.lon]),
            { color: '#1769aa', dashArray: '6, 6' }
        ).addTo(map);
    }

    countLabel.textContent = `${points.length} điểm`;
}

map.on('click', event => {
    points.push({
        lat: Number(event.latlng.lat.toFixed(7)),
        lon: Number(event.latlng.lng.toFixed(7))
    });
    updateArea();
});

document.getElementById('undo-point').addEventListener('click', () => {
    points.pop();
    updateArea();
});

document.getElementById('clear-area').addEventListener('click', () => {
    points.length = 0;
    updateArea();
});

confirmButton.addEventListener('click', () => {
    if (points.length < 3) {
        window.alert('Hãy chọn ít nhất 3 điểm để tạo khu vực tìm kiếm.');
        return;
    }
    if (!mapBridge) {
        window.alert('Chưa kết nối được với ứng dụng Python.');
        return;
    }

    mapBridge.save_search_area(JSON.stringify(points));
});

document.getElementById('generate-path').addEventListener('click', () => {
    if (points.length < 3) {
        document.getElementById('message').textContent =
            'Hãy chọn ít nhất 3 điểm trước khi tạo đường quét.';
        return;
    }
    if (!mapBridge) {
        document.getElementById('message').textContent =
            'Chưa kết nối được với ứng dụng Python.';
        return;
    }

    const spacing = Number(document.getElementById('spacing').value);
    mapBridge.generate_coverage_path(JSON.stringify(points), spacing);
});

new QWebChannel(qt.webChannelTransport, channel => {
    mapBridge = channel.objects.mapBridge;
    mapBridge.status_changed.connect(message => {
        document.getElementById('message').textContent = message;
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
});
