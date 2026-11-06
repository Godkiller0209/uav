# AGENTS.md — UAV Search and Rescue Project

## 1. TỔNG QUAN DỰ ÁN

Tôi đang phát triển một hệ thống mô phỏng UAV bầy đàn (UAV Swarm) phục vụ tìm kiếm và cứu nạn, cứu hộ (Search and Rescue — SAR).

Mục tiêu cuối cùng là xây dựng một ứng dụng Python có giao diện đồ họa, cho phép người dùng xác định khu vực tìm kiếm trên bản đồ, tự động tạo đường bay bao phủ khu vực, phân chia nhiệm vụ cho nhiều UAV, điều khiển UAV trong môi trường mô phỏng và theo dõi hoạt động của chúng.

Hệ thống dự kiến sử dụng:

- Python: ngôn ngữ lập trình chính.
- PyQt5: xây dựng giao diện desktop.
- PyQtWebEngine: nhúng bản đồ web vào ứng dụng Python.
- HTML, CSS, JavaScript: xây dựng và xử lý tương tác trên bản đồ.
- Leaflet: thư viện bản đồ tương tác.
- MapTiler: cung cấp dữ liệu bản đồ.
- PX4 SITL: mô phỏng phần mềm điều khiển bay PX4.
- Gazebo: mô phỏng môi trường và động lực học UAV.
- MAVSDK-Python: thư viện Python để điều khiển UAV.
- MAVLink: giao thức trao đổi lệnh điều khiển và dữ liệu UAV.
- asyncio: xử lý các tác vụ bất đồng bộ, đặc biệt là kết nối và điều khiển nhiều UAV.

Ưu tiên kiến trúc Python/PyQt5 kết hợp MAVSDK, không sử dụng ROS2 ở giai đoạn hiện tại trừ khi có lý do kỹ thuật rõ ràng và được tôi đồng ý.

## 2. MỤC TIÊU CUỐI CÙNG

Hệ thống cần phát triển theo các chức năng sau:

1. Hiển thị bản đồ trong giao diện PyQt5.
2. Cho phép người dùng click để đánh dấu các điểm và vẽ polygon biểu diễn khu vực tìm kiếm.
3. Truyền danh sách tọa độ GPS từ JavaScript về Python.
4. Lưu và quản lý khu vực tìm kiếm.
5. Chuyển tọa độ GPS sang hệ tọa độ phẳng XY phù hợp để tính toán hình học.
6. Sinh đường bay bao phủ khu vực bằng thuật toán Boustrophedon hoặc Zigzag Coverage Path Planning.
7. Tối ưu hướng quét, khoảng cách giữa các đường bay và thứ tự waypoint.
8. Chia khu vực thành nhiều nhiệm vụ nhỏ.
9. Xây dựng hàm chi phí và thuật toán phân công nhiệm vụ cho nhiều UAV.
10. Kết nối Python với PX4 SITL thông qua MAVSDK/MAVLink.
11. Điều khiển UAV cất cánh, bay theo waypoint và hạ cánh.
12. Khởi chạy và quản lý nhiều UAV trong PX4 SITL + Gazebo.
13. Phân phối nhiệm vụ và giám sát nhiều UAV đồng thời.
14. Hiển thị vị trí GPS, độ cao, vận tốc, pin, trạng thái và đường bay thực tế của UAV trên bản đồ.
15. Ghi log và đánh giá hiệu quả tìm kiếm qua các chỉ số như tỷ lệ bao phủ, thời gian, quãng đường và năng lượng ước tính.

Đây là mục tiêu dài hạn. Không triển khai tất cả chức năng cùng lúc.

## 3. TIẾN ĐỘ HIỆN TẠI

Dự án đang được phát triển trên Windows bằng VS Code và Python.

Cấu trúc thư mục hiện tại:

uav_code/
├── AGENTS.md
├── main.py
├── GUI/
│   ├── __init__.py
│   ├── main_window.py
│   └── map_bridge.py
├── mission/
│   ├── __init__.py
│   ├── coverage_path.py
│   ├── zigzag.py
│   └── waypoint_store.py
├── assets/
│   ├── map.html
│   └── map.js
└── data/
    ├── search_areas.json
    └── waypoints.json

Các thành phần đã có:

- `main.py`: điểm bắt đầu chạy ứng dụng; hiện tạo `QApplication`, mở `GPSMap` và chạy vòng lặp Qt. Chức năng đọc/in tọa độ đã lưu hiện chưa được tích hợp trong `main.py`.
- `GUI/main_window.py`: tạo cửa sổ PyQt5, nhúng trang bản đồ và thiết lập QWebChannel.
- `GUI/map_bridge.py`: nạp/lưu danh sách polygon qua QWebChannel, kiểm tra dữ liệu, đọc định dạng cũ nếu có, gọi lập tuyến nhiều khu vực và lưu waypoint.
- `GUI/__init__.py`: đánh dấu `GUI` là package Python.
- `mission/coverage_path.py`: điều phối thuật toán tạo tuyến qua toàn bộ khu vực theo thứ tự danh sách.
- `mission/zigzag.py`: chuyển từng polygon GPS sang XY cục bộ, tạo làn quét Zigzag và sắp waypoint dựa trên vị trí bắt đầu.
- `mission/waypoint_store.py`: lưu tuyến tổng hợp vào `data/waypoints.json` và xóa tuyến khi danh sách khu vực hoặc vị trí bắt đầu UAV thay đổi.
- `mission/__init__.py`: đánh dấu `mission` là package Python.
- `assets/map.html` và `assets/map.js`: trang Leaflet, quản lý nhiều polygon, chọn vị trí UAV giả lập và hiển thị tuyến cùng waypoint.
- `data/search_areas.json`: dữ liệu hiện tại chứa danh sách nhiều polygon. `.gitignore` bỏ qua file dữ liệu cục bộ này.
- `data/waypoints.json`: lưu tuyến Zigzag liên tục mới nhất qua toàn bộ polygon; schema version 2; `.gitignore` bỏ qua dữ liệu tọa độ cục bộ.
- File `data/search_area.json` theo định dạng cũ đã được xóa sau khi người dùng yêu cầu. Mã bridge vẫn giữ khả năng đọc file cũ nếu file đó có ở một bản cài đặt khác.
- Python đã tạo các thư mục `__pycache__` trong `GUI/` và `mission/`. Đây là bytecode tự sinh khi Python nạp module; chúng không phải mã nguồn. Sự tồn tại của chúng xác nhận các module đã được nạp ít nhất một lần, nhưng không xác nhận thao tác vẽ polygon hoặc tạo đường quét chạy đúng.
- PyQt5, PyQtWebEngine, Leaflet và MapTiler được dùng trong ứng dụng. Bản đồ cần kết nối internet để tải tài nguyên bên ngoài.

Tiến độ chức năng:

- Giai đoạn 1 — Hiển thị bản đồ trong PyQt5: code khởi tạo cửa sổ và nạp trang bản đồ đang có; chưa chạy lại để xác nhận hoạt động trong trạng thái hiện tại.
- Giai đoạn 2 — Vẽ polygon và truyền GPS về Python: code hiện hỗ trợ tạo nhiều polygon, chọn polygon, đổi tên, xóa từng polygon, xem tọa độ, gửi toàn bộ danh sách qua QWebChannel và lưu vào `data/search_areas.json`. Bridge vẫn có thể nạp `data/search_area.json` cũ nếu file đó tồn tại ở bản cài đặt khác. Chưa chạy xác nhận giao diện và luồng lưu/nạp nhiều polygon.
- Giai đoạn 3 — Chuyển GPS sang XY và sinh waypoint Zigzag: code hiện cho phép chọn vị trí UAV giả lập, áp dụng Zigzag cho toàn bộ polygon theo thứ tự danh sách, dùng vị trí UAV để chọn waypoint đầu của khu vực đầu tiên và điểm cuối khu vực trước để chọn waypoint đầu khu vực tiếp theo. Waypoint được đánh số liên tục; tuyến tổng hợp được lưu trong `data/waypoints.json` và hiển thị bằng nét đứt đỏ. Thay đổi danh sách khu vực hoặc vị trí UAV sẽ xóa tuyến lưu cũ. Chưa chạy kiểm tra giao diện hoặc thuật toán. Đoạn chuyển giữa các làn/khu vực có thể ra ngoài polygon; hướng quét cố định và tuyến chưa gửi tới UAV.
- Giai đoạn 4 — Phân chia khu vực và phân công nhiệm vụ: chưa triển khai.
- Giai đoạn 5 — Điều khiển một UAV bằng MAVSDK: đã học và thử nghiệm một số nội dung, cần kiểm tra lại code thực tế trước khi đánh giá mức độ hoàn thành.
- Giai đoạn 6 — Kết nối đường bay sinh tự động với PX4 SITL: chưa hoàn thành.
- Giai đoạn 7 — Điều khiển nhiều UAV đồng thời: chưa triển khai hoàn chỉnh.
- Giai đoạn 8 — Đánh giá và hoàn thiện hệ thống: chưa triển khai.

Lưu ý: Tiến độ trong tài liệu là bản ghi tại lần rà soát gần nhất, không thay thế việc kiểm tra mã nguồn hiện tại. Không khẳng định một chức năng hoạt động chỉ dựa trên việc đã có code; cần phân biệt rõ đã viết, đã chạy thử và đã xác nhận.

## 4. TIẾN ĐỘ GIAI ĐOẠN 2 VÀ NHIỆM VỤ HIỆN TẠI

Giai đoạn 2 đã có phần triển khai trong code nhưng cần chạy và xác nhận lại cùng ứng dụng. Hiện giao diện hỗ trợ nhiều polygon; dữ liệu cũ được đọc như polygon đầu tiên và file định dạng mới chỉ được tạo khi người dùng lưu thay đổi. Giai đoạn đang được triển khai là giai đoạn 3, với phần mở rộng quản lý nhiều polygon.

### Tiêu chí giai đoạn 2

Mục tiêu cụ thể:

1. Người dùng click trên bản đồ để thêm các điểm.
2. Mỗi điểm được đánh dấu bằng marker.
3. Các điểm được nối thành polygon khi có đủ số điểm cần thiết.
4. Có chức năng xóa điểm hoặc xóa toàn bộ polygon.
5. Có chức năng xác nhận khu vực tìm kiếm.
6. JavaScript lưu danh sách tọa độ GPS của các điểm.
7. Dùng QWebChannel để truyền dữ liệu từ JavaScript về Python.
8. Python nhận, kiểm tra và lưu danh sách tọa độ.
9. Hiển thị danh sách tọa độ trên giao diện hoặc vùng thông tin của ứng dụng.
10. Có thể xuất polygon thành JSON để dùng trong các giai đoạn tiếp theo.

Phần quản lý nhiều polygon hiện được tổ chức như sau:

- Mỗi polygon có `id`, `name` và danh sách `coordinates`.
- Python lưu một tài liệu JSON có `schema_version` và danh sách `areas` trong `data/search_areas.json`.
- JavaScript cho phép vẽ polygon mới, hoàn thành/lưu, chọn từ danh sách hoặc click trên bản đồ, đổi tên, xóa và xem tọa độ.
- Khi mở ứng dụng, bridge ưu tiên file mới; nếu chưa có thì thử đọc `data/search_area.json` cũ thành một polygon trong bộ nhớ. Bản làm việc hiện tại không còn file cũ này.
- Nút tạo tuyến gửi toàn bộ polygon đã lưu; thứ tự tuyến theo thứ tự trong danh sách.
- Khi xóa, đổi tên hoặc thay đổi danh sách polygon, tuyến waypoint cũ bị xóa để tránh dùng lộ trình không còn khớp.
- Cần chạy xác nhận nạp legacy, tạo nhiều polygon, lưu, khởi động lại, tạo tuyến tổng hợp, đánh số waypoint liên tục và kiểm tra xóa tuyến cũ khi danh sách khu vực đổi.

Dữ liệu đầu ra dự kiến:

[
    {"lat": 21.0285, "lon": 105.8542},
    {"lat": 21.0295, "lon": 105.8562},
    {"lat": 21.0275, "lon": 105.8572},
    {"lat": 21.0265, "lon": 105.8552}
]

Các tọa độ trên chỉ là dữ liệu minh họa, không phải dữ liệu khu vực tìm kiếm thực tế.

Nên dùng `QWebChannel`, `QObject`, `pyqtSignal` và `pyqtSlot` theo đúng cách của PyQt5 để giao tiếp giữa JavaScript và Python.

Không gán trực tiếp một hàm Python vào thuộc tính của đối tượng bridge để giả lập signal. Nếu cần phát sự kiện từ bridge về giao diện Python, hãy khai báo signal rõ ràng và kết nối bằng `.connect()`.

Chưa cần kết nối PX4 hoặc Gazebo trong giai đoạn 2.

### Nhiệm vụ hiện tại: giai đoạn 3

Mục tiêu là chuyển polygon GPS sang hệ tọa độ phẳng cục bộ, tạo các làn quét bên trong polygon và hiển thị kết quả trên bản đồ.

- `mission/zigzag.py` dùng phép chiếu equirectangular cục bộ quanh tâm gần đúng của từng polygon, tính bằng mét; `mission/coverage_path.py` điều phối nhiều polygon.
- Các đường quét hiện chạy theo một hướng cố định. Khoảng cách người dùng nhập được dùng làm khoảng cách tối đa giữa các làn; thuật toán chia đều khu vực theo chiều cao.
- Mỗi đoạn giao của một làn quét với polygon được dùng nội bộ để lập tuyến; không hiển thị riêng các đoạn quét. Tuyến waypoint liên tục được vẽ bằng nét đứt màu đỏ.
- Người dùng có thể bật/tắt chế độ chọn vị trí UAV; click bản đồ đặt hoặc dời marker xanh lá. Vị trí này chỉ tồn tại trong phiên hiện tại.
- Với polygon đầu tiên, waypoint đầu là đầu mút gần UAV nhất trong hai đoạn quét biên. Mỗi polygon tiếp theo chọn đầu mút biên gần waypoint cuối của polygon trước. Số waypoint chạy liên tục qua tất cả polygon.
- Các làn hiện song song trục X vì thuật toán thay đổi tọa độ Y để tạo làn và lấy các đoạn theo trục X. Có thể mở rộng bằng cách xoay polygon sang hệ XY tạm theo góc quét, tạo làn trong hệ đó rồi xoay waypoint trở lại. Bước tiếp theo nên cho người dùng chọn góc trước; tự động thử và tối ưu góc sẽ làm sau khi cách xoay được kiểm chứng.
- Cần chạy ứng dụng và kiểm tra polygon lồi/lõm, các khoảng cách quét khác nhau, polygon không hợp lệ và vị trí đường quét trên bản đồ trước khi xác nhận giai đoạn 3.
- Chưa tối ưu hướng quét, kiểm tra các đoạn chuyển tiếp có nằm trong vùng an toàn hay không, hoặc kết nối PX4/Gazebo. Tuyến hiện được lưu trong `data/waypoints.json`.

## 5. NGUYÊN TẮC KIẾN TRÚC

Phát triển hệ thống theo hướng module hóa, dễ hiểu, dễ kiểm thử và dễ mở rộng.

Kiến trúc dự kiến trong tương lai:

- `GUI/`: các thành phần giao diện PyQt5.
- `web/` hoặc `assets/`: HTML, CSS, JavaScript và tài nguyên bản đồ.
- `mission/`: xử lý khu vực, sinh đường bay và phân công nhiệm vụ.
- `drone/`: đối tượng UAV, lệnh điều khiển và telemetry.
- `communication/`: giao tiếp MAVSDK/MAVLink.
- `simulation/`: hỗ trợ khởi chạy và quản lý mô phỏng.
- `config/`: các tham số cấu hình.
- `data/`: nhiệm vụ đã lưu và log.

Không cần tạo toàn bộ cấu trúc ngay bây giờ. Chỉ tách module khi có nhu cầu thực tế.

Các nguyên tắc bắt buộc:

1. Thuật toán đường bay không phụ thuộc trực tiếp vào GUI hoặc PX4.
2. Module xử lý polygon không chịu trách nhiệm điều khiển UAV.
3. Module điều khiển UAV không chứa thuật toán sinh đường Zigzag.
4. GUI gọi các module nghiệp vụ thông qua giao diện rõ ràng.
5. Mỗi UAV cần có định danh và cấu hình kết nối riêng khi mở rộng sang nhiều UAV.
6. Tách cấu hình khỏi logic chương trình khi phù hợp.
7. Không sử dụng biến toàn cục tùy tiện.
8. Không đưa toàn bộ chương trình vào một file lớn.
9. Dùng đường dẫn tương đối dựa trên `__file__` khi cần truy cập tài nguyên của dự án; không phụ thuộc vào thư mục làm việc hiện tại.
10. Không viết sẵn toàn bộ hệ thống giả định rằng các module tương lai đã tồn tại.

## 6. NGUYÊN TẮC LẬP TRÌNH VÀ THIẾT KẾ GIAO DIỆN

Tôi đang học Python và phát triển dự án theo từng bước. Vì vậy:

- Khi tôi hỏi về một khái niệm, dòng code, cấu trúc dữ liệu, thuật toán hoặc quyết định thiết kế, hãy giải thích theo trình tự từ dễ đến khó:
  1. Nêu rõ nó là gì và dùng để giải quyết vấn đề gì.
  2. Giải thích ý tưởng hoặc nhu cầu dẫn đến cách làm đó; nếu biết nguồn gốc lịch sử hay bối cảnh kỹ thuật có liên quan thì nói ngắn gọn, không suy đoán khi không chắc.
  3. Đưa ví dụ đời thường hoặc ví dụ Python nhỏ, đơn giản và độc lập với dự án.
  4. Giải thích từng phần trong cú pháp, cấu trúc hoặc các bước của thuật toán bằng ngôn ngữ dễ hiểu.
  5. Sau đó mới liên hệ trực tiếp với file, đoạn code và luồng chạy trong dự án UAV SAR.
  6. Nếu phù hợp, chỉ ra dữ liệu đầu vào, kết quả đầu ra và điều gì xảy ra theo từng bước khi chạy.
- Với một dòng code cụ thể, giải thích vai trò của từng thành phần quan trọng (tên hàm, dấu ngoặc, chuỗi, biến, toán tử, từ khóa...) và vì sao cách viết đó tạo ra kết quả tương ứng.
- Với thuật toán, trước tiên giải thích bài toán cần giải, ý tưởng bằng ví dụ nhỏ hoặc hình dung từng bước; sau đó mới trình bày giả mã hoặc code và cách thuật toán áp dụng vào nhiệm vụ UAV.
- Dùng ví dụ minh họa ngắn, có kết quả cụ thể khi hữu ích. Không chỉ đưa định nghĩa hoặc lặp lại tên cú pháp; cần nối rõ nguyên nhân, cách hoạt động và kết quả.
- Điều chỉnh độ sâu theo câu hỏi: nếu tôi hỏi “giải thích chi tiết”, hãy giải thích kỹ từng bước; nếu tôi hỏi ngắn hoặc chỉ cần một định nghĩa, vẫn nêu mục đích nhưng tránh lan man.
- Giữ cách giải thích thân thiện với người đang học lập trình; giải nghĩa thuật ngữ mới trước khi dựa vào thuật ngữ đó.
- Viết code rõ ràng, dễ đọc, ưu tiên cách triển khai đơn giản trước.
- Đặt tên biến, hàm và class có ý nghĩa.
- Giải thích các thành phần mới và những đoạn code quan trọng.
- Không sử dụng kỹ thuật phức tạp nếu chưa cần thiết.
- Không viết code quá ngắn hoặc quá nhiều logic trong một hàm.
- Không tự ý thay đổi kiến trúc đã thống nhất.
- Không xóa chức năng đang hoạt động chỉ để viết lại theo phong cách khác.
- Ưu tiên giữ giao diện và hành vi hiện có khi bổ sung tính năng.
- Giải thích rõ các thư viện mới và lý do sử dụng.
- Với các chức năng liên quan đến asyncio và PyQt5, tránh chặn luồng giao diện.
- Nếu cần dùng thread hoặc event loop riêng, giải thích cách chúng phối hợp trước khi triển khai phức tạp.

Khi sửa code hiện có, hãy kiểm tra các file liên quan và hiểu luồng chạy của chương trình trước khi thay đổi.

## 7. QUY TRÌNH LÀM VIỆC VỚI CODEX

Khi nhận một yêu cầu mới:

Bước 1: Kiểm tra cấu trúc thư mục và các file liên quan.

Bước 2: Đọc code hiện có, xác định cách ứng dụng đang hoạt động.

Bước 3: Nêu ngắn gọn kế hoạch sửa đổi trước khi thực hiện các thay đổi lớn.

Bước 4: Chỉ sửa những phần cần thiết cho nhiệm vụ hiện tại.

Bước 5: Nếu cần tạo hoặc sửa file, ghi rõ file nào được thay đổi và mục đích của từng thay đổi.

Bước 6: Kiểm tra cú pháp, import, đường dẫn tài nguyên và các lỗi có thể kiểm tra được.

Bước 7: Chạy các bài kiểm thử phù hợp nếu môi trường cho phép.

Bước 8: Báo cáo những gì đã hoàn thành, những gì chưa kiểm thử được và các lệnh tôi cần chạy thủ công.

Không tự động chuyển sang giai đoạn tiếp theo nếu nhiệm vụ hiện tại chưa hoàn thành.

Không tự ý cài đặt phần mềm hệ thống, thay đổi môi trường PX4, xóa dữ liệu hoặc thực hiện lệnh có nguy cơ phá hủy dữ liệu mà chưa hỏi tôi.

Trước khi thay đổi nhiều file, hãy cân nhắc việc sử dụng Git để tạo checkpoint. Không tự commit hoặc push nếu tôi chưa yêu cầu.

## 8. QUẢN LÝ API KEY VÀ THÔNG TIN NHẠY CẢM

MapTiler API key hiện được sử dụng để tải bản đồ.

- Không in hoặc đưa API key vào tài liệu, log hay báo cáo nếu không cần thiết.
- Không commit API key hoặc thông tin nhạy cảm lên GitHub.
- Kiểm tra `.gitignore` và hướng dẫn cấu hình trước khi lưu thông tin bí mật vào file.
- API key sử dụng trong JavaScript phía trình duyệt có thể bị người khác quan sát; không coi đó là bí mật tuyệt đối.
- Nếu cần bảo vệ key tốt hơn, hãy đề xuất cấu hình giới hạn domain/origin hoặc các biện pháp phù hợp với loại ứng dụng.
- Không tự ý thay đổi hoặc xóa key đang hoạt động.

## 9. LỘ TRÌNH PHÁT TRIỂN BẮT BUỘC

Thực hiện lần lượt:

Giai đoạn 1: Hiển thị bản đồ trong PyQt5 — đã hoàn thành phần cơ bản.

Giai đoạn 2: Vẽ polygon, truyền GPS về Python và lưu JSON.

Giai đoạn 3: Chuyển tọa độ GPS sang XY và sinh đường bay Boustrophedon/Zigzag — đã có phiên bản đầu, cần kiểm thử và hoàn thiện.

Giai đoạn 4: Chia khu vực tìm kiếm và xây dựng thuật toán phân công nhiệm vụ.

Giai đoạn 5: Hoàn thiện kết nối, telemetry và lệnh điều khiển một UAV bằng MAVSDK.

Giai đoạn 6: Đưa đường bay sinh tự động vào PX4 SITL và kiểm thử một UAV.

Giai đoạn 7: Quản lý nhiều PX4 SITL instance, nhiều UAV và nhiệm vụ đồng thời.

Giai đoạn 8: Hoàn thiện GUI, ghi log, đánh giá hiệu quả và viết báo cáo.

Ở mỗi giai đoạn, cần xác định tiêu chí hoàn thành cụ thể và kiểm thử trước khi chuyển tiếp.

## 10. YÊU CẦU KHI BẮT ĐẦU LÀM VIỆC

Trước khi sửa đổi, hãy đọc file AGENTS.md và kiểm tra các file liên quan trong cấu trúc hiện tại: `main.py`, `GUI/main_window.py`, `GUI/map_bridge.py`, `assets/map.html`, `assets/map.js` và module nghiệp vụ tương ứng trong `mission/`.

Ở đầu một nhiệm vụ mới, hãy xác định giai đoạn hiện tại từ code thực tế, phân biệt phần đã viết với phần đã chạy xác nhận, rồi nêu ngắn gọn kế hoạch nếu công việc có thay đổi nhiều thành phần. Không dựa vào đường dẫn file cũ như `GUI/gui_1.py` nếu file đó không còn tồn tại.

Mục tiêu là phát triển dự án có kiểm soát, giải thích các thay đổi dễ hiểu và giữ cho chương trình chạy được sau mỗi bước.
