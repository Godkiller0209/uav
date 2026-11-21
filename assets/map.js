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
let isChoosingUavPosition = false;
let isChoosingSpiralCenter = false;
let spiralCenter = null;
let uavPosition = null;
let uavMarker = null;
let mapBridge = null;
let liveUavTelemetry = { connected: false };
let routeStartPosition = null;
let routeStartSource = null;
let liveUavMarker = null;
let liveTrackPoints = [];

const savedAreaLayer = L.layerGroup().addTo(map);
const draftLayer = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);
const spiralLayer = L.layerGroup().addTo(map);
const waypointLayer = L.layerGroup().addTo(map);
const missionRouteLayer = L.layerGroup().addTo(map);
const missionWaypointLayer = L.layerGroup().addTo(map);
const liveTrackLayer = L.layerGroup().addTo(map);
const liveUavLayer = L.layerGroup().addTo(map);

const countLabel = document.getElementById('area-count');
const areaList = document.getElementById('area-list');

window.invalidateMapSize = () => map.invalidateSize();

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

function clearDisplayedRoute() {
    routeLayer.clearLayers();
    waypointLayer.clearLayers();
    spiralLayer.clearLayers();
    routeStartPosition = null;
    routeStartSource = null;
}

function setSpiralCenter(latlng) {
    spiralCenter = {
        lat: Number(latlng.lat.toFixed(7)),
        lon: Number(latlng.lng.toFixed(7))
    };
    isChoosingSpiralCenter = false;
    document.getElementById('choose-spiral-center').classList.remove('mode-active');
    clearDisplayedRoute();
    L.circleMarker([spiralCenter.lat, spiralCenter.lon], {
        radius: 8,
        color: '#795000',
        weight: 3,
        fillColor: '#ffca28',
        fillOpacity: 1
    }).bindTooltip('Tâm Archimedean Spiral').addTo(spiralLayer);
    showMessage(
        `Đã chọn tâm Spiral: ${spiralCenter.lat}, ${spiralCenter.lon}. `
        + 'Bấm Generate Trajectory để tạo lại.'
    );
}

function renderArchimedeanTrajectory(trajectory) {
    routeLayer.clearLayers();
    waypointLayer.clearLayers();
    spiralLayer.clearLayers();
    if (trajectory.center) {
        L.circleMarker([trajectory.center.lat, trajectory.center.lon], {
            radius: 8,
            color: '#795000',
            weight: 3,
            fillColor: '#ffca28',
            fillOpacity: 1
        }).bindTooltip('Tâm Archimedean Spiral').addTo(spiralLayer);
    }
    trajectory.segments.forEach((segment, index) => {
        const points = segment.map(point => [point.lat, point.lon]);
        L.polyline(points, {
            color: '#e53935',
            weight: 4,
            opacity: 0.95
        }).bindTooltip(`Spiral segment ${index + 1}`).addTo(spiralLayer);
    });
    const ratio = trajectory.coverage_ratio === null
        ? 'chưa tính' : `${(trajectory.coverage_ratio * 100).toFixed(1)}%`;
    showMessage(
        `Archimedean Spiral · ${trajectory.area_name}: `
        + `${trajectory.segments.length} đoạn, đứt ${trajectory.discontinuity_count} lần, `
        + `dài ${trajectory.path_length_m.toFixed(1)} m, coverage ước lượng ${ratio}. `
        + 'Các đoạn rời nhau không được tự nối.'
    );
}

function renderMissionRoute(waypoints) {
    missionRouteLayer.clearLayers();
    missionWaypointLayer.clearLayers();
    if (!Array.isArray(waypoints) || waypoints.length === 0) {
        return;
    }

    const points = waypoints.map(point => [point.lat, point.lon]);
    L.polyline(points, {
        color: '#00acc1',
        weight: 4,
        opacity: 0.9
    }).addTo(missionRouteLayer);

    waypoints.forEach((point, index) => {
        L.circleMarker([point.lat, point.lon], {
            radius: 5,
            color: '#004d5a',
            weight: 2,
            fillColor: '#26c6da',
            fillOpacity: 1
        }).bindTooltip(`Mission Waypoint ${index + 1}`).addTo(missionWaypointLayer);
    });
}

function clearLiveUav() {
    liveUavLayer.clearLayers();
    liveTrackLayer.clearLayers();
    liveUavMarker = null;
    liveTrackPoints = [];
}

function hasValidLiveUavPosition(telemetry) {
    return Boolean(
        telemetry
        && telemetry.connected
        && Number.isFinite(telemetry.lat)
        && Number.isFinite(telemetry.lon)
    );
}

function updateStartPositionButton() {
    const button = document.getElementById('choose-uav-position');
    if (!button) {
        return;
    }

    if (hasValidLiveUavPosition(liveUavTelemetry)) {
        isChoosingUavPosition = false;
        button.disabled = true;
        button.classList.remove('mode-active');
        button.textContent = '✓ GPS UAV thật đang dùng';
        button.title = 'Điểm gốc tạo waypoint lấy từ GPS Telemetry hiện tại.';

        if (uavMarker) {
            map.removeLayer(uavMarker);
            uavMarker = null;
        }
        uavPosition = null;
        return;
    }

    button.disabled = false;
    button.textContent = '📍 Điểm gốc giả lập (offline)';
    button.title = 'Chỉ dùng làm điểm gốc khi chưa có GPS Telemetry thật.';
}

function updateLiveUav(telemetry) {
    const hadLivePosition = hasValidLiveUavPosition(liveUavTelemetry);
    liveUavTelemetry = telemetry && typeof telemetry === 'object'
        ? { ...telemetry }
        : { connected: false };
    const hasLivePosition = hasValidLiveUavPosition(liveUavTelemetry);

    if (!hadLivePosition && hasLivePosition && routeStartSource === 'manual') {
        clearDisplayedRoute();
        if (mapBridge) {
            mapBridge.clear_saved_waypoints();
        }
    }

    updateStartPositionButton();
    if (!hasLivePosition) {
        clearLiveUav();
        return;
    }

    const position = [liveUavTelemetry.lat, liveUavTelemetry.lon];
    const previous = liveTrackPoints[liveTrackPoints.length - 1];
    if (!previous || previous[0] !== position[0] || previous[1] !== position[1]) {
        liveTrackPoints.push(position);
        if (liveTrackPoints.length > 2000) {
            liveTrackPoints.shift();
        }
        liveTrackLayer.clearLayers();
        if (liveTrackPoints.length > 1) {
            L.polyline(liveTrackPoints, {
                color: '#1565c0',
                weight: 4,
                opacity: 0.8
            }).addTo(liveTrackLayer);
        }
    }

    const heading = Number.isFinite(liveUavTelemetry.heading_deg)
        ? liveUavTelemetry.heading_deg
        : 0;
    const icon = L.divIcon({
        className: 'live-uav-icon',
        html: `<span style="transform: rotate(${heading}deg)">▲</span>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16]
    });
    if (!liveUavMarker) {
        liveUavMarker = L.marker(position, { icon }).addTo(liveUavLayer);
    } else {
        liveUavMarker.setLatLng(position);
        liveUavMarker.setIcon(icon);
    }

    const altitude = Number.isFinite(liveUavTelemetry.relative_altitude_m)
        ? `${liveUavTelemetry.relative_altitude_m.toFixed(1)} m` : '—';
    liveUavMarker.bindTooltip(
        `UAV 1 · Telemetry thật<br>${liveUavTelemetry.lat.toFixed(7)}, `
        + `${liveUavTelemetry.lon.toFixed(7)}<br>Độ cao tương đối: ${altitude}`
    );
}

function setUavPosition(latlng) {
    uavPosition = {
        lat: Number(latlng.lat.toFixed(7)),
        lon: Number(latlng.lng.toFixed(7))
    };

    if (uavMarker) {
        map.removeLayer(uavMarker);
    }
    uavMarker = L.circleMarker(
        [uavPosition.lat, uavPosition.lon],
        {
            radius: 9,
            color: '#1b5e20',
            weight: 3,
            fillColor: '#43a047',
            fillOpacity: 1
        }
    ).bindTooltip('Điểm gốc giả lập (offline)').addTo(map);
    clearDisplayedRoute();
    if (mapBridge) {
        mapBridge.clear_saved_waypoints();
    }

    showMessage(
        `Đã chọn điểm gốc giả lập: ${uavPosition.lat}, ${uavPosition.lon}. `
        + 'Bấm lại nút để thoát chế độ chọn.'
    );
}

function renderSavedAreas() {
    savedAreaLayer.clearLayers();
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
                if (isChoosingSpiralCenter) {
                    setSpiralCenter(event.latlng);
                } else if (isChoosingUavPosition) {
                    setUavPosition(event.latlng);
                } else if (!isDrawing) {
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
    clearDisplayedRoute();

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
    if (areaId !== selectedAreaId) {
        spiralCenter = null;
        clearDisplayedRoute();
    }
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
    if (isChoosingSpiralCenter) {
        setSpiralCenter(event.latlng);
        return;
    }
    if (isChoosingUavPosition) {
        setUavPosition(event.latlng);
        return;
    }
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

document.getElementById('choose-uav-position').addEventListener('click', event => {
    if (hasValidLiveUavPosition(liveUavTelemetry)) {
        showMessage('Đang có GPS Telemetry thật; điểm gốc ảo đã bị vô hiệu hóa.');
        return;
    }

    isChoosingUavPosition = !isChoosingUavPosition;
    event.currentTarget.classList.toggle('mode-active', isChoosingUavPosition);

    if (isChoosingUavPosition) {
        isChoosingSpiralCenter = false;
        document.getElementById('choose-spiral-center').classList.remove('mode-active');
        showMessage('Chế độ offline: click bản đồ để chọn điểm gốc giả lập màu xanh.');
    } else {
        showMessage('Đã thoát chế độ chọn điểm gốc giả lập.');
    }
});

document.getElementById('choose-spiral-center').addEventListener('click', event => {
    isChoosingSpiralCenter = !isChoosingSpiralCenter;
    event.currentTarget.classList.toggle('mode-active', isChoosingSpiralCenter);
    if (isChoosingSpiralCenter) {
        isChoosingUavPosition = false;
        document.getElementById('choose-uav-position').classList.remove('mode-active');
        showMessage('Click trong polygon đang chọn để đặt tâm Spiral.');
    } else {
        showMessage('Tâm hiện tại được giữ lại. Dùng nút “Dùng tâm Spiral tự động” để xóa lựa chọn này.');
    }
});

document.getElementById('automatic-spiral-center').addEventListener('click', () => {
    spiralCenter = null;
    isChoosingSpiralCenter = false;
    document.getElementById('choose-spiral-center').classList.remove('mode-active');
    clearDisplayedRoute();
    showMessage('Tâm xoắn sẽ do Python tự chọn bên trong polygon.');
});

document.getElementById('trajectory-algorithm').addEventListener('change', () => {
    clearDisplayedRoute();
    const isSpiral = document.getElementById('trajectory-algorithm').value
        === 'archimedean_spiral';
    updateTrajectoryControls();
    if (isSpiral) {
        isChoosingUavPosition = false;
        document.getElementById('choose-uav-position').classList.remove('mode-active');
    } else {
        isChoosingSpiralCenter = false;
        document.getElementById('choose-spiral-center').classList.remove('mode-active');
    }
    if (isSpiral && spiralCenter) {
        L.circleMarker([spiralCenter.lat, spiralCenter.lon], {
            radius: 8,
            color: '#795000',
            weight: 3,
            fillColor: '#ffca28',
            fillOpacity: 1
        }).bindTooltip('Tâm Archimedean Spiral').addTo(spiralLayer);
    }
    showMessage(isSpiral
        ? 'Archimedean Spiral sẽ được tạo cho polygon đang chọn.'
        : 'Zigzag sẽ tạo waypoint cho tất cả polygon đã lưu.');
});

function updateTrajectoryControls() {
    const isSpiral = document.getElementById('trajectory-algorithm').value
        === 'archimedean_spiral';
    document.getElementById('spiral-options').hidden = !isSpiral;
    document.getElementById('choose-uav-position').hidden = isSpiral;
    document.querySelector('label[for="spacing"]').textContent = isSpiral
        ? 'Khoảng cách giữa các vòng xoắn (m)'
        : 'Khoảng cách giữa các làn Zigzag (m)';
}

updateTrajectoryControls();

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
    spiralCenter = null;
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
    clearDisplayedRoute();
    renderSavedAreas();
    saveAreas();
});

document.getElementById('delete-area').addEventListener('click', () => {
    const selectedArea = getSelectedArea();
    if (!selectedArea) {
        showMessage('Hãy chọn polygon cần xóa.');
        return;
    }
    if (!window.confirm(
            `Xóa ${selectedArea.name}? Các tuyến đã tạo cho khu vực sẽ bị xóa.`)) {
        return;
    }
    if (!mapBridge) {
        showMessage('Chưa kết nối được với ứng dụng Python.');
        return;
    }

    const deletedAreaId = selectedArea.id;
    spiralCenter = null;
    areas = areas.filter(area => area.id !== deletedAreaId);
    selectedAreaId = areas.length > 0 ? areas[0].id : null;
    clearDisplayedRoute();
    renderSavedAreas();
    saveAreas();
});

document.getElementById('generate-path').addEventListener('click', () => {
    if (areas.length === 0) {
        showMessage('Hãy lưu ít nhất một polygon trước khi tạo tuyến.');
        return;
    }
    if (!mapBridge) {
        showMessage('Chưa kết nối được với ứng dụng Python.');
        return;
    }

    const algorithm = document.getElementById('trajectory-algorithm').value;
    const spacing = Number(document.getElementById('spacing').value);
    if (algorithm === 'archimedean_spiral') {
        const selectedArea = getSelectedArea();
        if (!selectedArea) {
            showMessage('Hãy chọn polygon cần tạo Archimedean Spiral.');
            return;
        }
        const footprint = Number(document.getElementById('footprint-width').value);
        const initialRadius = Number(document.getElementById('initial-radius').value);
        if (!Number.isFinite(spacing) || spacing <= 0
                || !Number.isFinite(footprint) || footprint <= 0
                || !Number.isFinite(initialRadius) || initialRadius < 0) {
            showMessage('Spacing và footprint phải lớn hơn 0; bán kính ban đầu không âm.');
            return;
        }
        mapBridge.generate_archimedean_spiral(
            JSON.stringify(selectedArea), spacing, initialRadius,
            JSON.stringify(spiralCenter), footprint
        );
        return;
    }

    mapBridge.latest_live_uav_telemetry(telemetryJson => {
        let telemetry;
        try {
            telemetry = JSON.parse(telemetryJson);
        } catch (error) {
            showMessage(`Không đọc được GPS Telemetry UAV: ${error}`);
            return;
        }

        updateLiveUav(telemetry);
        const startPosition = hasValidLiveUavPosition(telemetry)
            ? { lat: telemetry.lat, lon: telemetry.lon }
            : uavPosition;
        if (!startPosition) {
            showMessage(
                'Chưa có GPS UAV thật. Hãy kết nối UAV hoặc chọn điểm gốc giả lập offline.'
            );
            return;
        }

        mapBridge.generate_coverage_path(
            JSON.stringify(areas),
            spacing,
            JSON.stringify(startPosition)
        );
    });
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
        spiralLayer.clearLayers();
        routeStartPosition = coveragePath.start_position
            || (hasValidLiveUavPosition(liveUavTelemetry)
                ? { lat: liveUavTelemetry.lat, lon: liveUavTelemetry.lon }
                : uavPosition);
        routeStartSource = coveragePath.start_source
            || (hasValidLiveUavPosition(liveUavTelemetry) ? 'telemetry' : 'manual');
        routeLayer.clearLayers();
        waypointLayer.clearLayers();

        const routePoints = [routeStartPosition, ...coveragePath.waypoints]
            .filter(Boolean)
            .map(point => [point.lat, point.lon]);
        L.polyline(routePoints, {
            color: '#d32f2f',
            weight: 3,
            opacity: 0.9,
            dashArray: '8, 7'
        }).addTo(routeLayer);

        coveragePath.waypoints.forEach((point, index) => {
            const firstWaypointClass = index === 0 ? ' waypoint-first' : '';
            const icon = L.divIcon({
                className: `waypoint-icon${firstWaypointClass}`,
                html: `<span>${index + 1}</span>`,
                iconSize: [28, 28],
                iconAnchor: [14, 14]
            });
            L.marker([point.lat, point.lon], { icon })
                .bindTooltip(`Waypoint ${index + 1}`)
                .addTo(waypointLayer);
        });
    });
    mapBridge.trajectory_ready.connect(trajectoryJson => {
        renderArchimedeanTrajectory(JSON.parse(trajectoryJson));
    });
    mapBridge.mission_route_changed.connect(routeJson => {
        renderMissionRoute(JSON.parse(routeJson));
    });
    mapBridge.live_uav_telemetry_changed.connect(telemetryJson => {
        updateLiveUav(JSON.parse(telemetryJson));
    });
    mapBridge.latest_mission_route(routeJson => {
        renderMissionRoute(JSON.parse(routeJson));
    });
    mapBridge.latest_live_uav_telemetry(telemetryJson => {
        updateLiveUav(JSON.parse(telemetryJson));
    });
    mapBridge.load_search_areas();
});
