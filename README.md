# Ariston Custom — Home Assistant custom integration

Integration tự viết cho bình nóng lạnh Ariston, dựa trên API cloud dịch ngược
từ APK `com.remotethermo.aristonnet` v7.0.2.40360
(xem `../re-api-spec.md`).

## Điểm khác với bản fork `ariston_net`

- Domain riêng `ariston_custom` — không xung đột với integration `ariston`
  có sẵn của HA core (2026.8+) và không đụng bản custom cũ.
- Code theo spec đã dịch ngược đầy đủ: header `ar.authToken` (không phải Bearer),
  body `{"new":X,"old":Y}`, login lại khi 401 (API v2 không có refresh-token).
- Poll trạng thái 60s, năng lượng riêng 30 phút.

## Hỗ trợ hiện tại

- **SLIM TOP** (`wheType = SplitLongPipe` → endpoint `/v2/velis/slpPlantData/...`).
  Các loại bình khác (Velis thường, Med...) chưa hỗ trợ — cấu trúc code đã tách
  sẵn để mở rộng (`api.py` nhóm theo loại plant).

## Tính năng

- **water_heater**: bật/tắt, đặt nhiệt độ, operation modes
  (`manual`, `program_green`, `program_comfort`, `program_fast`,
  `program_auto`, `program_hchp`, `program_electric`, `program_greenplus`).
- **sensor**: nhiệt độ nước hiện tại, nhiệt độ mục tiêu, điện năng tiêu thụ (kWh).

## Cài đặt

1. Copy thư mục `custom_components/ariston_custom` vào
   `<config>/custom_components/` của Home Assistant.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **Ariston Custom**.
4. Nhập email + mật khẩu tài khoản Ariston → chọn bình → xong.

## Lưu ý

- Chạy qua **cloud** (bình không có API local).
- Tài khoản được lưu trong config entry để tự login lại khi token hết hạn.
- Không chạy song song 2 integration Ariston trên cùng tài khoản.
