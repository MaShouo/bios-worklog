# BIOS 分类建议

分类用于顶层检索，不要求一次选择很多。通常选 1–3 个稳定分类，再用 `tags` 保存平台、芯片或具体模块词。

## 固件阶段

- SEC
- PEI
- DXE
- BDS
- SMM
- Runtime
- Recovery

## 启动与平台

- Boot
- Fast Boot
- Capsule
- Firmware Update
- Setup
- Manufacturing
- Performance
- Reset
- Watchdog

## 电源与 ACPI

- ACPI
- S3
- S4
- S5
- Modern Standby
- Wake
- Thermal
- Power Management

## 内存、总线与设备

- Memory
- Memory Training
- PCI
- PCIe
- USB
- SATA
- NVMe
- SMBus
- I2C
- SPI
- GPIO
- Clock

## 显示、输入与外围

- Display
- Graphics
- GOP
- Audio
- Keyboard
- Touchpad
- Camera
- Sensor
- Dock
- Thunderbolt

## 安全

- Secure Boot
- TPM
- Measured Boot
- Firmware Signing
- Authentication
- Variable Security
- SMM Security

## 协同组件与系统

- EC
- BMC
- ME
- PSP
- FSP
- Microcode
- Windows
- Linux
- Hypervisor

## 测试和质量

- Build
- Flash
- Regression
- Stability
- Compatibility
- Compliance
- Validation

## 标签建议

`categories` 保持稳定，`tags` 可以更具体，例如：

- 芯片/控制器：`AlderLake-P`、`XHCI`、`PEG0`
- 规范/表：`_PTS`、`_WAK`、`OpRegion`
- 症状：`black-screen`、`hang`、`boot-loop`
- 工具：`CHIPSEC`、`WinDbg`、`UEFITool`
- 构建分支或板型（确认符合保密要求后再写）

不要把未经确认的根因当作分类。可先作为 tag 或写入“当前判断”。
