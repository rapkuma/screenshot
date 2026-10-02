# 관련 패키지 설치
# pip install pyautogui pillow reportlab pyinstaller PyQt5 keyboard mss dxcam

import sys
import os
import json
import time
import logging
import traceback
import keyboard
import pyautogui
import mss
from PIL import Image
import img2pdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QRadioButton, QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QButtonGroup, QDesktopWidget, QFileDialog, QTextEdit, QProgressBar, QCheckBox
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QPen, QColor
import re

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.rect = QRect()

    def set_rect(self, x1, y1, x2, y2):
        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        if w > 0 and h > 0:
            self.setGeometry(x, y, w, h)
            self.rect = QRect(0, 0, w, h)
            self.show()
            self.update()

    def paintEvent(self, event):
        if not self.rect.isValid():
            return
        painter = QPainter(self)
        pen = QPen(QColor(255, 0, 0), 3, Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

class SelectionWindow(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.start_point = None
        self.end_point = None

        desktop = QApplication.desktop()
        rect = QRect()
        for i in range(desktop.screenCount()):
            rect = rect.united(desktop.screenGeometry(i))
        self.setGeometry(rect)

    def show_fullscreen(self):
        self.start_point = None
        self.end_point = None
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if self.start_point and self.end_point:
            rect = QRect(self.start_point, self.end_point).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor(255, 0, 0), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            self.end_point = self.start_point
            self.update()

    def mouseMoveEvent(self, event):
        if self.start_point:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_point:
            self.end_point = event.pos()
            rect = QRect(self.start_point, self.end_point).normalized()

            global_start = self.mapToGlobal(rect.topLeft())
            global_end = self.mapToGlobal(rect.bottomRight())

            self.main_app.left_x_input.setText(str(global_start.x()))
            self.main_app.left_y_input.setText(str(global_start.y()))
            self.main_app.right_x_input.setText(str(global_end.x()))
            self.main_app.right_y_input.setText(str(global_end.y()))
            
            self.main_app.save_settings()

            self.hide()
            self.main_app.showNormal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.main_app.showNormal()

class ConvertPdfApp(QWidget):
    def __init__(self):
        super().__init__()
        self.count_down = 5 # 처음 타이머 시간
        self.user_delay = 3 # 사용자 마우스 이동 대기시간
        self.top_left_x = 0
        self.top_left_y = 0
        self.bottom_right_x = 0
        self.bottom_right_y = 0
        self.total_pages = 0
        self.current_page = 0
        self.output_dir = os.path.join(os.path.expanduser("~"), "Documents")
        self.overlay = OverlayWindow()
        self.selection_window = SelectionWindow(self)
        self.initUI()

    def initUI(self):
        # 좌상단 좌표 설정 버튼
        self.top_left_label = QLabel('좌상단 좌표:')
        self.left_x_input = QLineEdit(self)
        self.left_y_input = QLineEdit(self)
        self.left_x_input.setPlaceholderText("x 좌표")
        self.left_y_input.setPlaceholderText("y 좌표")
        self.left_x_input.textChanged.connect(self.update_overlay)
        self.left_y_input.textChanged.connect(self.update_overlay)
        self.top_left_button = QPushButton('좌상단 좌표 설정', self)
        self.top_left_button.clicked.connect(self.set_left_top_coordinates)

        # 우하단 좌표 설정 버튼
        self.bottom_right_label = QLabel('우하단 좌표:')
        self.right_x_input = QLineEdit(self)
        self.right_y_input = QLineEdit(self)
        self.right_x_input.setPlaceholderText("x 좌표")
        self.right_y_input.setPlaceholderText("y 좌표")
        self.right_x_input.textChanged.connect(self.update_overlay)
        self.right_y_input.textChanged.connect(self.update_overlay)
        self.bottom_right_button = QPushButton('우하단 좌표 설정', self)
        self.bottom_right_button.clicked.connect(self.set_right_bottom_coordinates)

        # 다음 페이지 방향키 라디오 버튼
        self.next_button_label = QLabel('다음 페이지 방향키:')
        self.up_radio = QRadioButton('위', self)
        self.down_radio = QRadioButton('아래', self)
        self.left_radio = QRadioButton('왼쪽', self)
        self.right_radio = QRadioButton('오른쪽', self)

        # 라디오 버튼 그룹
        self.radio_group = QButtonGroup(self)
        self.radio_group.addButton(self.up_radio)
        self.radio_group.addButton(self.down_radio)
        self.radio_group.addButton(self.left_radio)
        self.radio_group.addButton(self.right_radio)
        self.radio_group.buttonClicked.connect(self.save_settings) # 라디오 버튼 변경 시 자동 저장

        # 디렉토리 선택 버튼 및 경로 표시
        self.dir_button = QPushButton('저장 경로 선택', self)
        self.dir_button.clicked.connect(self.select_directory)
        self.dir_label = QLabel('저장 경로가 선택되지 않았습니다.')

        # PDF 파일명 입력
        self.pdf_label = QLabel('PDF 파일명:')
        self.pdf_input = QLineEdit(self)
        self.pdf_input.textChanged.connect(self.save_settings)

        # 저장 폴더명 자동 생성 체크박스
        self.subfolder_checkbox = QCheckBox('PDF 파일명과 동일한 하위 폴더 생성', self)
        self.subfolder_checkbox.stateChanged.connect(self.save_settings)

        # 총 페이지 수 및 딜레이 설정
        self.total_pages_label = QLabel('총 페이지 수:')
        self.total_pages_input = QLineEdit(self)
        self.total_pages_input.setPlaceholderText("예: 100")
        self.total_pages_input.textChanged.connect(self.save_settings)
        self.total_pages_input.textChanged.connect(self.update_progress_max)

        self.pages_per_shot_label = QLabel('한 화면당 페이지 수(면):')
        self.pages_per_shot_input = QLineEdit(self)
        self.pages_per_shot_input.setText("1")
        self.pages_per_shot_input.textChanged.connect(self.save_settings)
        self.pages_per_shot_input.textChanged.connect(self.update_progress_max)

        # 딜레이 설정 (초)
        self.delay_label = QLabel('딜레이(초):')
        self.delay_input = QLineEdit(self)
        self.delay_input.setText("1.0")
        self.delay_input.textChanged.connect(self.save_settings)

        # 실행 및 저장 버튼
        self.save_button = QPushButton('설정 저장', self)
        self.save_button.clicked.connect(self.manual_save_settings)
        
        self.folder_to_pdf_button = QPushButton('폴더 내 이미지로 PDF 만들기', self)
        self.folder_to_pdf_button.clicked.connect(self.convert_folder_to_pdf)
        self.folder_to_pdf_button.setMinimumHeight(35)

        self.run_button = QPushButton('스크린샷 찍고 PDF 만들기 (시작)', self)
        self.run_button.clicked.connect(self.run_screenshot_to_pdf)
        self.run_button.setMinimumHeight(45)
        self.run_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")

        # 프로그래스 바 추가
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(25)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        # %p: 퍼센트, %v: 현재 값, %m: 최대 값
        self.progress_bar.setFormat("%p% (%v/%m)")
        self.progress_bar.setTextVisible(True)

        # 로그 출력 영역
        self.log_textbox = QTextEdit(self)
        self.log_textbox.setReadOnly(True)
        self.log_textbox.setMinimumHeight(100)
        self.log_textbox.setPlaceholderText("여기에 작업 진행 상황이 표시됩니다...")

        # 레이아웃 설정
        layout = QVBoxLayout()

        # 좌상단 좌표 설정 레이아웃
        top_left_layout = QHBoxLayout()
        top_left_layout.addWidget(self.top_left_label)
        top_left_layout.addWidget(self.left_x_input)
        top_left_layout.addWidget(self.left_y_input)
        top_left_layout.addWidget(self.top_left_button)
        layout.addLayout(top_left_layout)

        # 우하단 좌표 설정 레이아웃
        bottom_right_layout = QHBoxLayout()
        bottom_right_layout.addWidget(self.bottom_right_label)
        bottom_right_layout.addWidget(self.right_x_input)
        bottom_right_layout.addWidget(self.right_y_input)
        bottom_right_layout.addWidget(self.bottom_right_button)
        layout.addLayout(bottom_right_layout)

        # 드래그로 영역 설정 레이아웃
        self.drag_button = QPushButton('마우스 드래그로 캡처 영역 지정하기', self)
        self.drag_button.setMinimumHeight(40)
        self.drag_button.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        self.drag_button.clicked.connect(self.start_drag_selection)
        layout.addWidget(self.drag_button)

        # 라디오 버튼 레이아웃
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.next_button_label)
        button_layout.addWidget(self.up_radio)
        button_layout.addWidget(self.down_radio)
        button_layout.addWidget(self.left_radio)
        button_layout.addWidget(self.right_radio)
        layout.addLayout(button_layout)

        # 디렉토리 선택 버튼 및 경로 표시 레이아웃
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.dir_button)
        dir_layout.addWidget(self.dir_label)
        layout.addLayout(dir_layout)

        # PDF 파일명 입력 레이아웃
        pdf_layout = QHBoxLayout()
        pdf_layout.addWidget(self.pdf_label)
        pdf_layout.addWidget(self.pdf_input)
        pdf_layout.addWidget(self.subfolder_checkbox)
        layout.addLayout(pdf_layout)

        # 총 페이지 수 및 딜레이 입력 레이아웃
        total_pages_layout = QHBoxLayout()
        total_pages_layout.addWidget(self.total_pages_label)
        total_pages_layout.addWidget(self.total_pages_input)
        total_pages_layout.addWidget(self.pages_per_shot_label)
        total_pages_layout.addWidget(self.pages_per_shot_input)
        total_pages_layout.addWidget(self.delay_label)
        total_pages_layout.addWidget(self.delay_input)
        layout.addLayout(total_pages_layout)

        # 프로그래스 바 및 로그 출력 위젯 추가
        layout.addWidget(QLabel('작업 진행률:'))
        layout.addWidget(self.progress_bar)
        layout.addWidget(QLabel('진행 상황 로그:'))
        layout.addWidget(self.log_textbox)

        # 실행 및 저장 버튼 추가
        button_action_layout = QVBoxLayout()
        
        save_folder_layout = QHBoxLayout()
        save_folder_layout.addWidget(self.save_button)
        save_folder_layout.addWidget(self.folder_to_pdf_button)
        button_action_layout.addLayout(save_folder_layout)
        
        button_action_layout.addWidget(self.run_button)
        layout.addLayout(button_action_layout)

        self.setLayout(layout)
        self.setWindowTitle('Screenshot convert to PDF')
        self.center()
        self.load_settings()
        self.update_progress_max()

    def center(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def closeEvent(self, event):
        self.overlay.close()
        self.selection_window.close()
        self.save_settings()
        event.accept()

    def start_drag_selection(self):
        self.selection_window.show_fullscreen()

    def log_message(self, msg):
        self.log_textbox.append(msg)
        print(msg)
        QApplication.processEvents()

    def manual_save_settings(self):
        self.save_settings()

    def save_settings(self):
        try:
            settings = {
                'left_x': self.left_x_input.text(),
                'left_y': self.left_y_input.text(),
                'right_x': self.right_x_input.text(),
                'right_y': self.right_y_input.text(),
                'direction': self.radio_group.checkedButton().text() if self.radio_group.checkedButton() else '',
                'output_dir': self.output_dir,
                'use_subfolder': self.subfolder_checkbox.isChecked(),
                'pdf_filename': self.pdf_input.text(),
                'total_pages': self.total_pages_input.text(),
                'pages_per_shot': self.pages_per_shot_input.text(),
                'delay': self.delay_input.text()
            }
            with open('settings.json', 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            print("Settings saved successfully to settings.json")
        except Exception as e:
            self.log_message(f"설정 저장 중 오류 발생: {e}")

    def load_settings(self):
        if os.path.exists('settings.json'):
            try:
                with open('settings.json', 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.left_x_input.setText(settings.get('left_x', ''))
                    self.left_y_input.setText(settings.get('left_y', ''))
                    self.right_x_input.setText(settings.get('right_x', ''))
                    self.right_y_input.setText(settings.get('right_y', ''))

                    direction = settings.get('direction', '')
                    if direction == '위':
                        self.up_radio.setChecked(True)
                    elif direction == '아래':
                        self.down_radio.setChecked(True)
                    elif direction == '왼쪽':
                        self.left_radio.setChecked(True)
                    elif direction == '오른쪽':
                        self.right_radio.setChecked(True)

                    self.output_dir = settings.get('output_dir', '')
                    if self.output_dir:
                        self.dir_label.setText(f'저장 경로: {self.output_dir}')

                    self.pdf_input.setText(settings.get('pdf_filename', ''))
                    self.subfolder_checkbox.setChecked(settings.get('use_subfolder', False))
                    self.total_pages_input.setText(settings.get('total_pages', ''))
                    self.pages_per_shot_input.setText(settings.get('pages_per_shot', '1'))
                    self.delay_input.setText(settings.get('delay', '1.0'))

                    if self.left_x_input.text() and self.left_y_input.text():
                        self.top_left_x = int(self.left_x_input.text())
                        self.top_left_y = int(self.left_y_input.text())
                    if self.right_x_input.text() and self.right_y_input.text():
                        self.bottom_right_x = int(self.right_x_input.text())
                        self.bottom_right_y = int(self.right_y_input.text())
            except Exception as e:
                print(f"설정을 불러오는 중 오류 발생: {e}")
            self.update_overlay()
            self.update_progress_max()

    def update_progress_max(self):
        try:
            pages = int(self.total_pages_input.text())
            per_shot = int(self.pages_per_shot_input.text())
            if per_shot <= 0: per_shot = 1
            import math
            shots = math.ceil(pages / per_shot)
            self.progress_bar.setMaximum(max(1, shots))
            self.progress_bar.setValue(0)
        except (ValueError, ZeroDivisionError):
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)

    def update_overlay(self):
        try:
            x1 = int(self.left_x_input.text())
            y1 = int(self.left_y_input.text())
            x2 = int(self.right_x_input.text())
            y2 = int(self.right_y_input.text())
            self.overlay.set_rect(x1, y1, x2, y2)
        except ValueError:
            self.overlay.hide()

    def set_left_top_coordinates(self):
        time.sleep(self.user_delay)  # 사용자에게 이동 시간을 주기 위해 대기
        self.top_left_x, self.top_left_y = pyautogui.position()
        self.left_x_input.setText(str(self.top_left_x))
        self.left_y_input.setText(str(self.top_left_y))
        print(f"x, y coordinates set to: ({self.top_left_x}, {self.top_left_y})")

    def set_right_bottom_coordinates(self):
        time.sleep(self.user_delay)  # 사용자에게 이동 시간을 주기 위해 대기
        self.bottom_right_x, self.bottom_right_y = pyautogui.position()
        self.right_x_input.setText(str(self.bottom_right_x))
        self.right_y_input.setText(str(self.bottom_right_y))
        print(f"x, y coordinates set to: ({self.bottom_right_x}, {self.bottom_right_y})")

    def select_directory(self):
        default_path = self.output_dir if self.output_dir else os.path.expanduser("~")
        new_path = QFileDialog.getExistingDirectory(self, '저장 경로 선택', default_path)
        if new_path: # 취소하지 않고 경로를 선택한 경우에만 업데이트
            self.output_dir = new_path
            self.dir_label.setText(f'저장 경로: {self.output_dir}')
            # 폴더명을 PDF 파일명으로 제안
            folder_name = os.path.basename(self.output_dir)
            if folder_name:
                self.pdf_input.setText(folder_name)
            self.save_settings()

    def run_screenshot_to_pdf(self):
        # 좌표 확인
        if (not self.left_x_input.text().strip() or not self.left_y_input.text().strip() or not self.right_x_input.text().strip() or not self.right_y_input.text().strip()):
            QMessageBox.warning(self, '입력 오류', '좌상단 및 우하단 좌표를 설정하세요.')
            return

        # 다음 페이지 버튼 설정 확인
        selected_button = self.radio_group.checkedButton()
        if selected_button is None:
            QMessageBox.warning(self, '입력 오류', '방향 버튼을 선택하세요.')
            return
        button_to_click = selected_button.text()

        # 저장 경로 확인
        if not self.output_dir:
            QMessageBox.warning(self, '입력 오류', '저장 경로를 선택하세요.')
            return

        # PDF 파일명 확인
        pdf_filename = self.pdf_input.text()
        if not pdf_filename:
            QMessageBox.warning(self, '입력 오류', 'PDF 파일명을 입력하세요.')
            return
        if not pdf_filename.endswith('.pdf'):
            pdf_filename += '.pdf'

        # 총 페이지 수 및 캡처 횟수(면 수 반영) 확인
        try:
            pages = int(self.total_pages_input.text())
            per_shot = int(self.pages_per_shot_input.text())
            if per_shot <= 0: per_shot = 1
            # 실제 스크린샷 찍어야 할 횟수 계산
            import math
            self.total_pages = math.ceil(pages / per_shot)
            self.progress_bar.setMaximum(self.total_pages)
        except ValueError:
            QMessageBox.warning(self, '입력 오류', '유효한 총 페이지 수와 면 수를 입력하세요.')
            return

        # 스크린샷 및 PDF 변환 실행
        self.run_button.setEnabled(False) # 실행 중 버튼 비활성화
        
        # 하위 폴더 자동 생성 여부 확인
        original_output_dir = self.output_dir
        if self.subfolder_checkbox.isChecked():
            # PDF 파일명(확장자 제외)으로 폴더 생성
            subfolder = pdf_filename.rsplit('.', 1)[0]
            target_subfolder_path = os.path.join(self.output_dir, subfolder)
            
            if os.path.exists(target_subfolder_path):
                # 이미 폴더가 존재하는 경우 경고 팝업
                reply = QMessageBox.question(self, '경고', 
                                           f"폴더 '{subfolder}'가 이미 존재합니다. 계속하시겠습니까?\n기존 파일이 덮어씌워질 수 있습니다.", 
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    self.run_button.setEnabled(True) # 버튼 복구
                    return
            else:
                try:
                    os.makedirs(target_subfolder_path)
                    self.log_message(f"폴더 생성됨: {target_subfolder_path}")
                except Exception as e:
                    self.log_message(f"폴더 생성 실패: {e}")
            
            self.output_dir = target_subfolder_path

        self.current_page = 0
        try:
            self.take_screenshot_and_convert_to_pdf(self.left_x_input.text(), self.left_y_input.text(), self.right_x_input.text(), self.right_y_input.text(), button_to_click, pdf_filename)
        finally:
            self.run_button.setEnabled(True) # 완료 후 버튼 다시 활성화
            self.output_dir = original_output_dir # 경로 원상 복구
            # 총 페이지 수는 다시 입력된 값으로 유지 (설정 저장 등을 위해)
            pass

    def convert_folder_to_pdf(self):
        # 1. 폴더 선택
        folder_path = QFileDialog.getExistingDirectory(self, '이미지가 들어있는 폴더 선택', self.output_dir)
        if not folder_path:
            return
        
        # 2. 이미지 파일 수집 (확장자 필터링)
        valid_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif')
        image_files = []
        for f in os.listdir(folder_path):
            if f.lower().endswith(valid_extensions):
                image_files.append(os.path.join(folder_path, f))
        
        if not image_files:
            QMessageBox.warning(self, '오류', '선택한 폴더에 이미지 파일이 없습니다.')
            return
        
        # 3. 자연어 정렬 (파일명 내 숫자 크기대로 정렬 예: 2 -> 10)
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower()
                    for text in re.split('([0-9]+)', s)]
        
        image_files.sort(key=natural_sort_key)
        
        # 4. PDF 파일명 입력 (기본값은 폴더명)
        default_pdf_name = os.path.basename(folder_path) + ".pdf"
        from PyQt5.QtWidgets import QInputDialog
        pdf_name, ok = QInputDialog.getText(self, 'PDF 파일명 입력', '저장할 PDF 파일명을 입력하세요:', QLineEdit.Normal, default_pdf_name)
        
        if ok and pdf_name:
            if not pdf_name.lower().endswith('.pdf'):
                pdf_name += '.pdf'
            
            # 저장 경로 (현재 설정된 output_dir 또는 선택한 폴더 상위)
            # 여기서는 편의상 선택한 폴더 내부에 저장하도록 output_dir을 임시로 폴더 경로로 설정
            original_output_dir = self.output_dir
            self.output_dir = folder_path 
            
            self.convert_to_pdf(image_files, pdf_name)
            
            # 원상복구
            self.output_dir = original_output_dir
        
    def take_screenshot_and_convert_to_pdf(self, top_left_x, top_left_y, bottom_right_x, bottom_right_y, button, pdf_filename):
        try:
            delay_sec = float(self.delay_input.text())
        except ValueError:
            delay_sec = 1.0

        # dxcam 초기화 (캡처 보호 우회용 최후의 수단, DirectX GPU 직접 접근)
        camera = None
        try:
            import dxcam
            camera = dxcam.create(output_color="RGB")
        except Exception as e:
            print(f"DXCAM 초기화 실패: {e}")

        # 카운트다운 시작
        for i in range(self.count_down, 0, -1):
            if keyboard.is_pressed('esc'):
                self.log_message("ESC 키가 눌려 취소되었습니다.")
                return
            self.log_message(f"{i}초 후 스크린샷을 시작합니다.")
            # UI 응답성을 위해 0.1초 단위로 분할 대기
            for _ in range(10):
                time.sleep(0.1)
                QApplication.processEvents()

        self.log_message("스크린샷 캡처 및 페이지 넘기기를 시작합니다...")
        self.progress_bar.setValue(0)
        screenshot_filenames = []

        # 지정된 좌표로 마우스 이동 및 클릭
        for page in range(self.total_pages):
            # 페이지 번호 증가
            self.current_page += 1
            self.progress_bar.setValue(self.current_page)

            # 스크린샷 파일명 설정
            screenshot_filename = os.path.join(self.output_dir, f'image_{self.current_page}.png')
            self.log_message(f"[{self.current_page}/{self.total_pages}] 페이지 스크린샷 캡처 중...")

            # 좌표 값을 정수로 변환 후 음수 길이 방지를 위해 정렬
            x1 = int(top_left_x)
            y1 = int(top_left_y)
            x2 = int(bottom_right_x)
            y2 = int(bottom_right_y)

            x_min = min(x1, x2)
            y_min = min(y1, y2)
            x_max = max(x1, x2)
            y_max = max(y1, y2)

            # 스크린샷 찍기 (dxcam 엔진으로 하드웨어 캡처 보호 우회)
            width = x_max - x_min
            height = y_max - y_min

            img = None
            if camera:
                region = (x_min, y_min, x_max, y_max)
                # dxcam은 화면 갱신이 없으면 None을 반환하므로 여러 번 재시도
                for _ in range(20):
                    frame = camera.grab(region=region)
                    if frame is not None:
                        img = Image.fromarray(frame)
                        break
                    time.sleep(0.05)

            # fallback (dxcam 실패 시 mss 사용)
            if img is None:
                with mss.mss() as sct:
                    monitor = {"top": y_min, "left": x_min, "width": width, "height": height}
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            try:
                if not os.path.exists(self.output_dir):
                    os.makedirs(self.output_dir)
                img.save(screenshot_filename)
                screenshot_filenames.append(screenshot_filename)
                self.log_message(f"성공: {screenshot_filename} 저장됨")
            except Exception as e:
                self.log_message(f"이미지 저장 실패 ({self.current_page}페이지): {e}")
                QMessageBox.critical(self, '오류', f'{self.current_page}페이지 저장 중 오류가 발생했습니다.\n{e}')
                break

            # 총 페이지 수에 도달하면 종료
            if self.current_page >= self.total_pages:
                break

            if button == '위':
                pyautogui.press('up')
            elif button == '아래':
                pyautogui.press('down')
            elif button == '왼쪽':
                pyautogui.press('left')
            elif button == '오른쪽':
                pyautogui.press('right')

            # 설정한 딜레이만큼 대기 (ESC 키 감지를 위해 0.1초 단위로 짧게 나누어 대기)
            is_esc_pressed = False
            steps = max(1, int(delay_sec * 10))
            for _ in range(steps):
                if keyboard.is_pressed('esc'):
                    is_esc_pressed = True
                    break
                time.sleep(0.1)
                QApplication.processEvents()

            if is_esc_pressed:
                self.log_message("ESC 키가 눌려 스크린샷 캡처를 중단합니다.")
                break

        self.log_message("모든 캡처가 완료되었습니다. PDF 변환을 시작합니다...")
        # PDF로 변환
        self.convert_to_pdf(screenshot_filenames, pdf_filename)
        self.update_overlay()

    def convert_to_pdf(self, image_filenames, pdf_filename):
        if not image_filenames:
            return

        pdf_path = os.path.join(self.output_dir, pdf_filename)
        self.log_message(f"PDF 생성 시작 (img2pdf 엔진): {pdf_path}")

        try:
            # img2pdf: 이미지 데이터 재압축 없이 바이너리로 직접 PDF에 래핑하므로 매우 빠름
            with open(pdf_path, "wb") as f:
                f.write(img2pdf.convert(image_filenames))
            
            self.log_message(f"PDF 저장 성공: {pdf_path}")
            QMessageBox.information(self, '작업 완료', f'파일이 성공적으로 저장되었습니다.\n\n파일명: {pdf_filename}\n경로: {self.output_dir}')
        except Exception as e:
            self.log_message(f"PDF 변환 중 중대한 오류 발생: {e}")
            QMessageBox.critical(self, '오류', f'PDF 변환 중 오류가 발생했습니다.\n{e}')

        # 폴더 열기
        try:
            os.startfile(self.output_dir)
        except Exception as e:
            self.log_message(f"폴더 열기 오류: {e}")

if __name__ == "__main__":
    import ctypes
    try:
        # 윈도우 디스플레이 배율(DPI) 스케일링 무시 (PyQt와 PyAutoGUI 좌표 일치화)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    app = QApplication(sys.argv)
    
    # Unhandled Exception 발생 시 로그 파일에 기록
    def exception_hook(exctype, value, tb):
        error_msg = "".join(traceback.format_exception(exctype, value, tb))
        logging.error(f"CRASH: {error_msg}")
        QMessageBox.critical(None, '오류 발생', f'프로그램이 예기치 않게 종료될 수 있습니다. \n로그 확인(error.log): \n{value}')
        sys.__excepthook__(exctype, value, tb)

    # 로그 파일 설정
    logging.basicConfig(
        filename='error.log', 
        level=logging.ERROR,
        format='%(asctime)s [%(levelname)s] %(message)s',
        encoding='utf-8'
    )
    sys.excepthook = exception_hook

    ex = ConvertPdfApp()
    ex.show()
    sys.exit(app.exec_())