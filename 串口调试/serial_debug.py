#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口调试插件
"""

import sys
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QComboBox, QPushButton, QTextEdit, QCheckBox,
                            QGroupBox, QGridLayout, QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
import threading
import serial
import serial.tools.list_ports
from PyQt5.QtGui import QTextCursor
from plugin_interface import PluginInterface


class SerialReadThread(QThread):
    """串口读取线程"""
    data_received = pyqtSignal(bytes)

    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self.running = False

    def run(self):
        """运行线程"""
        self.running = True
        while self.running:
            try:
                if self.serial_port.in_waiting > 0:
                    # 读取数据
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    # 通过信号传递数据
                    self.data_received.emit(data)
            except Exception as e:
                if self.running:
                    print(f"读取串口数据错误: {str(e)}")
                break
            # 短暂休眠，避免CPU占用过高
            self.msleep(10)

    def stop(self):
        """停止线程"""
        self.running = False
        self.wait()


class SerialDebugWidget(QWidget):
    """串口调试部件"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.serial_port = None
        self.read_thread = None

        self.init_ui()
        self.refresh_ports()

    def init_ui(self):
        """初始化UI"""
        # 主布局
        layout = QVBoxLayout()

        # 串口设置组
        settings_group = QGroupBox("串口设置")
        settings_layout = QHBoxLayout()

        # 端口选择
        self.port_combo = QComboBox()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        settings_layout.addWidget(QLabel("端口:"))
        settings_layout.addWidget(self.port_combo)
        settings_layout.addWidget(self.refresh_btn)

        # 波特率选择
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems([
            "300", "600", "1200", "2400", "4800", "9600", "14400", "19200",
            "28800", "38400", "57600", "76800", "115200", "230400", "460800", "921600"
        ])
        self.baudrate_combo.setCurrentText("9600")
        settings_layout.addWidget(QLabel("波特率:"))
        settings_layout.addWidget(self.baudrate_combo)

        # 数据位选择
        self.databits_combo = QComboBox()
        self.databits_combo.addItems(["5", "6", "7", "8"])
        self.databits_combo.setCurrentText("8")
        settings_layout.addWidget(QLabel("数据位:"))
        settings_layout.addWidget(self.databits_combo)

        # 停止位选择
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])
        self.stopbits_combo.setCurrentText("1")
        settings_layout.addWidget(QLabel("停止位:"))
        settings_layout.addWidget(self.stopbits_combo)

        # 校验位选择
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["无", "奇", "偶"])
        self.parity_combo.setCurrentText("无")
        settings_layout.addWidget(QLabel("校验位:"))
        settings_layout.addWidget(self.parity_combo)

        # DTR和RTS控制按钮
        self.dtr_btn = QPushButton("DTR: 关")
        self.dtr_btn.setCheckable(True)
        self.dtr_btn.clicked.connect(self.toggle_dtr)
        self.dtr_btn.setEnabled(False)
        settings_layout.addWidget(self.dtr_btn)

        self.rts_btn = QPushButton("RTS: 关")
        self.rts_btn.setCheckable(True)
        self.rts_btn.clicked.connect(self.toggle_rts)
        self.rts_btn.setEnabled(False)
        settings_layout.addWidget(self.rts_btn)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # 操作按钮
        button_layout = QHBoxLayout()
        self.serial_btn = QPushButton("打开串口")
        self.serial_btn.setCheckable(True)
        self.serial_btn.clicked.connect(self.toggle_serial)

        button_layout.addWidget(self.serial_btn)
        layout.addLayout(button_layout)

        # 接收区域
        receive_splitter = QHBoxLayout()

        # 接收文本区域
        receive_text_group = QGroupBox("接收区域")
        receive_text_layout = QHBoxLayout()
        self.receive_text = QTextEdit()
        self.receive_text.setReadOnly(True)
        receive_text_layout.addWidget(self.receive_text)
        receive_text_group.setLayout(receive_text_layout)
        receive_splitter.addWidget(receive_text_group)

        # 接收设置
        receive_settings_group = QGroupBox("接收设置")
        receive_settings_layout = QVBoxLayout()
        self.hex_receive = QCheckBox("十六进制显示")
        self.hex_receive.stateChanged.connect(self.on_receive_format_changed)
        self.auto_scroll = QCheckBox("自动滚动")
        self.auto_scroll.setChecked(True)
        self.timestamp = QCheckBox("显示时间戳")
        receive_settings_layout.addWidget(self.hex_receive)
        receive_settings_layout.addWidget(self.auto_scroll)
        receive_settings_layout.addWidget(self.timestamp)
        receive_settings_layout.addStretch()

        # 接收按钮
        self.clear_btn = QPushButton("清空接收")
        self.clear_btn.clicked.connect(self.clear_receive)
        self.save_btn = QPushButton("保存数据")
        self.save_btn.clicked.connect(self.save_data)
        receive_settings_layout.addWidget(self.clear_btn)
        receive_settings_layout.addWidget(self.save_btn)

        receive_settings_group.setLayout(receive_settings_layout)
        receive_splitter.addWidget(receive_settings_group)

        # 添加到主布局
        layout.addLayout(receive_splitter)

        # 发送区域
        send_splitter = QHBoxLayout()

        # 发送文本区域
        send_text_group = QGroupBox("发送区域")
        send_text_layout = QVBoxLayout()

        # 文本编辑框
        self.send_text = QTextEdit()
        send_text_layout.addWidget(self.send_text)
        send_text_group.setLayout(send_text_layout)
        send_splitter.addWidget(send_text_group)

        # 发送设置
        send_settings_group = QGroupBox("发送设置")
        send_settings_layout = QVBoxLayout()
        self.hex_send = QCheckBox("十六进制发送")
        self.newline_send = QCheckBox("发送新行")
        send_settings_layout.addWidget(self.hex_send)
        send_settings_layout.addWidget(self.newline_send)
        send_settings_layout.addStretch()

        # 发送按钮
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_data)
        self.send_btn.setEnabled(False)
        self.clear_send_btn = QPushButton("清空")
        self.clear_send_btn.clicked.connect(lambda: self.send_text.clear())
        send_settings_layout.addWidget(self.send_btn)
        send_settings_layout.addWidget(self.clear_send_btn)

        send_settings_group.setLayout(send_settings_layout)
        send_splitter.addWidget(send_settings_group)

        # 添加到主布局
        layout.addLayout(send_splitter)



        # 设置布局
        self.setLayout(layout)

    def refresh_ports(self):
        """刷新可用串口列表"""
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)

    def toggle_serial(self):
        """切换串口状态（打开/关闭）"""
        if self.serial_btn.isChecked():
            # 打开串口
            self.open_serial()
        else:
            # 关闭串口
            self.close_serial()

    def open_serial(self):
        """打开串口"""
        port_name = self.port_combo.currentText()
        if not port_name:
            QMessageBox.warning(self, "错误", "请选择串口")
            self.serial_btn.setChecked(False)
            return

        try:
            # 设置串口参数
            baudrate = int(self.baudrate_combo.currentText())
            databits = int(self.databits_combo.currentText())

            # 设置停止位
            stopbits_map = {
                "1": serial.STOPBITS_ONE,
                "1.5": serial.STOPBITS_ONE_POINT_FIVE,
                "2": serial.STOPBITS_TWO
            }
            stopbits = stopbits_map[self.stopbits_combo.currentText()]

            # 设置校验位
            parity_map = {
                "无": serial.PARITY_NONE,
                "奇": serial.PARITY_ODD,
                "偶": serial.PARITY_EVEN
            }
            parity = parity_map[self.parity_combo.currentText()]

            # 打开串口
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=baudrate,
                bytesize=databits,
                parity=parity,
                stopbits=stopbits,
                timeout=1
            )

            # 先打开RTS信号
            self.serial_port.rts = True
            # 短暂延时
            import time
            time.sleep(0.1)
            # 关闭RTS信号
            self.serial_port.rts = False

            # 创建并启动读取线程
            self.read_thread = SerialReadThread(self.serial_port)
            self.read_thread.data_received.connect(self.on_data_received)
            self.read_thread.start()

            # 更新UI状态
            self.serial_btn.setText("关闭串口")
            self.send_btn.setEnabled(True)
            self.dtr_btn.setEnabled(True)
            self.rts_btn.setEnabled(True)

            # 禁用设置
            self.port_combo.setEnabled(False)
            self.baudrate_combo.setEnabled(False)
            self.databits_combo.setEnabled(False)
            self.stopbits_combo.setEnabled(False)
            self.parity_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)

            # 记录日志
            self.main_window.log_message(f"串口 {port_name} 已打开")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开串口 {port_name}: {str(e)}")
            self.serial_btn.setChecked(False)
            # 重置所有按钮状态
            self.send_btn.setEnabled(False)
            self.dtr_btn.setEnabled(False)
            self.rts_btn.setEnabled(False)

    def close_serial(self):
        """关闭串口"""
        if self.serial_port and self.serial_port.is_open:
            # 停止读取线程
            if self.read_thread:
                self.read_thread.stop()
                self.read_thread = None

            # 关闭串口
            try:
                self.serial_port.close()
            except:
                pass
            self.serial_port = None

            # 更新UI状态
            self.serial_btn.setText("打开串口")
            self.serial_btn.setChecked(False)
            self.send_btn.setEnabled(False)
            self.dtr_btn.setEnabled(False)
            self.dtr_btn.setChecked(False)
            self.dtr_btn.setText("DTR: 关")
            self.rts_btn.setEnabled(False)
            self.rts_btn.setChecked(False)
            self.rts_btn.setText("RTS: 关")

            # 启用设置
            self.port_combo.setEnabled(True)
            self.baudrate_combo.setEnabled(True)
            self.databits_combo.setEnabled(True)
            self.stopbits_combo.setEnabled(True)
            self.parity_combo.setEnabled(True)
            self.refresh_btn.setEnabled(True)

            # 记录日志
            self.main_window.log_message("串口已关闭")

    def on_data_received(self, data):
        """处理接收到的数据"""
        # 转换数据
        if self.hex_receive.isChecked():
            # 十六进制显示
            text = ' '.join([f'{b:02X}' for b in data])
        else:
            # 文本显示
            try:
                text = data.decode('utf-8', errors='replace')
            except:
                text = str(data)

        # 添加时间戳
        if self.timestamp.isChecked():
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            text = f"[{timestamp}] {text}"

        # 添加到接收区域
        self.receive_text.insertPlainText(text)

        # 自动滚动
        if self.auto_scroll.isChecked():
            cursor = self.receive_text.textCursor()
            cursor.movePosition(cursor.End)
            self.receive_text.setTextCursor(cursor)

        # 记录日志
        self.main_window.debug_message(f"接收到 {len(data)} 字节数据")

    def send_data(self):
        """发送数据"""
        if not self.serial_port or not self.serial_port.is_open:
            return

        text = self.send_text.toPlainText()
        if not text:
            return

        # 转换数据
        if self.hex_send.isChecked():
            # 十六进制发送
            try:
                # 移除空格和换行符
                hex_str = text.replace(' ', '').replace('\n', '').replace('\r', '')
                # 转换为字节
                data = bytes.fromhex(hex_str)
            except ValueError as e:
                QMessageBox.warning(self, "错误", f"无效的十六进制数据: {str(e)}")
                return
        else:
            # 文本发送
            data = text.encode('utf-8')

        # 添加新行
        if self.newline_send.isChecked():
            data += b'\r\n'

        # 发送数据
        try:
            bytes_written = self.serial_port.write(data)
            self.serial_port.flush()

            # 记录日志
            self.main_window.debug_message(f"发送了 {bytes_written} 字节数据")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"发送数据失败: {str(e)}")

    def on_receive_format_changed(self):
        """接收格式改变"""
        # 清空接收区域
        self.receive_text.clear()

    def clear_receive(self):
        """清空接收区域"""
        self.receive_text.clear()

    def save_data(self):
        """保存接收到的数据"""
        text = self.receive_text.toPlainText()
        if not text:
            QMessageBox.information(self, "提示", "没有数据可保存")
            return

        # 打开文件保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存数据", "", "文本文件 (*.txt);;所有文件 (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                QMessageBox.information(self, "成功", "数据保存成功")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"保存数据失败: {str(e)}")

    def toggle_dtr(self):
        """切换DTR信号状态"""
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.dtr = self.dtr_btn.isChecked()
                state = "开" if self.dtr_btn.isChecked() else "关"
                self.dtr_btn.setText(f"DTR: {state}")
                self.main_window.debug_message(f"DTR信号已设置为: {state}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"设置DTR失败: {str(e)}")
                self.dtr_btn.setChecked(False)
                self.dtr_btn.setText("DTR: 关")

    def toggle_rts(self):
        """切换RTS信号状态"""
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.rts = self.rts_btn.isChecked()
                state = "开" if self.rts_btn.isChecked() else "关"
                self.rts_btn.setText(f"RTS: {state}")
                self.main_window.debug_message(f"RTS信号已设置为: {state}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"设置RTS失败: {str(e)}")
                self.rts_btn.setChecked(False)
                self.rts_btn.setText("RTS: 关")


class SerialDebugPlugin(PluginInterface):
    """串口调试插件"""

    def get_name(self):
        """获取插件名称"""
        return "串口调试"

    def get_description(self):
        """获取插件描述"""
        return "提供串口通信调试功能，支持打开/关闭串口、发送/接收数据等功能"

    def get_version(self):
        """获取插件版本"""
        return "1.0.0"

    def get_author(self):
        """获取插件作者"""
        return "Zhang Yang"

    def initialize(self, main_window):
        """初始化插件"""
        self.main_window = main_window

        # 创建串口调试部件
        self.serial_widget = SerialDebugWidget(main_window)

        # 添加到主窗口
        main_window.tab_widget.addTab(self.serial_widget, "串口调试")

        # 记录日志
        main_window.log_message("串口调试插件已初始化")

    def activate(self):
        """激活插件"""
        # 切换到串口调试选项卡
        index = self.main_window.tab_widget.indexOf(self.serial_widget)
        if index >= 0:
            self.main_window.tab_widget.setCurrentIndex(index)

    def deactivate(self):
        """停用插件"""
        # 关闭串口
        if self.serial_widget.serial_port and self.serial_widget.serial_port.is_open:
            self.serial_widget.close_serial()
