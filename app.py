import sys
import time
import json
import os
import math
from datetime import datetime
from PyQt5.QtCore import (
    Qt, QObject, QThread, pyqtSignal, QPoint, QEvent, 
    QPropertyAnimation, QEasingCurve, QSize, QTimer,
    QRect, QPointF
)
from PyQt5.QtGui import (
    QIcon, QColor, QPainter, QPen, QBrush, QPainterPath, QFont,
    QLinearGradient, QGradient, QRadialGradient,
    QPalette, QPixmap, QImage, QKeyEvent, QMouseEvent
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, 
    QHBoxLayout, QWidget, QLabel, QStatusBar, QFileDialog,
    QGraphicsOpacityEffect, QProgressBar, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect, QStyle, QAction
)
import keyboard
import mouse


class ActionRecorder(QObject):
    """Worker class to handle recording user actions in a separate thread."""
    finished = pyqtSignal()
    action_recorded = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.is_recording = False
        self.actions = []
        self.start_time = None
    
    def start_recording(self):
        self.is_recording = True
        self.actions = []
        self.start_time = time.time()
        
        # Set up mouse event hooks
        mouse.hook(self.on_mouse_event)
        
        # Set up keyboard event hooks
        keyboard.hook(self.on_keyboard_event)
    
    def stop_recording(self):
        self.is_recording = False
        mouse.unhook_all()
        keyboard.unhook_all()
        self.finished.emit()
    
    def on_mouse_event(self, event):
        if not self.is_recording:
            return
        
        # Only record clicks, not movements
        if hasattr(event, 'event_type') and event.event_type in ('down', 'up'):
            timestamp = time.time() - self.start_time
            # Get current mouse position since ButtonEvent doesn't have x,y attributes
            x, y = mouse.get_position()
            action = {
                'type': 'mouse',
                'event_type': event.event_type,
                'button': event.button if hasattr(event, 'button') else 'unknown',
                'position': (x, y),
                'timestamp': timestamp
            }
            self.action_recorded.emit(action)
            self.actions.append(action)
    
    def on_keyboard_event(self, event):
        if not self.is_recording:
            return
        
        timestamp = time.time() - self.start_time
        action = {
            'type': 'keyboard',
            'event_type': event.event_type,
            'key': event.name,
            'timestamp': timestamp
        }
        self.action_recorded.emit(action)
        self.actions.append(action)


class ActionPlayer(QObject):
    """Worker class to handle replaying recorded actions in a separate thread."""
    finished = pyqtSignal()
    progress = pyqtSignal(int, int)  # current, total
    
    def __init__(self):
        super().__init__()
        self.actions = []
        self.is_playing = False
    
    def set_actions(self, actions):
        self.actions = actions
    
    def play_actions(self):
        self.is_playing = True
        total_actions = len(self.actions)
        
        if total_actions == 0:
            self.finished.emit()
            return
            
        # Sort actions by timestamp
        sorted_actions = sorted(self.actions, key=lambda x: x['timestamp'])
        
        for i, action in enumerate(sorted_actions):
            if not self.is_playing:
                break
                
            # Calculate the delay based on the timestamp
            current_time = action['timestamp']
            if i > 0:
                delay = current_time - sorted_actions[i-1]['timestamp']
                if delay > 0:
                    time.sleep(delay)
            
            # Perform the action
            if action['type'] == 'mouse':
                x, y = action['position']
                if action['event_type'] == 'down':
                    mouse.move(x, y)
                    mouse.press(button=action['button'])
                elif action['event_type'] == 'up':
                    mouse.release(button=action['button'])
            
            elif action['type'] == 'keyboard':
                if action['event_type'] == 'down':
                    keyboard.press(action['key'])
                elif action['event_type'] == 'up':
                    keyboard.release(action['key'])
            
            # Emit progress
            self.progress.emit(i + 1, total_actions)
        
        self.is_playing = False
        self.finished.emit()
    
    def stop_playing(self):
        self.is_playing = False


class MacroRecorderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Macro Recorder")
        self.setGeometry(100, 100, 500, 180)
        
        # Set app style - clean modern theme
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #F5F5F5;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #DDDDDD;
                border-radius: 4px;
                padding: 8px 16px;
                color: #333333;
                font-size: 13px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #EFEFEF;
                border: 1px solid #CCCCCC;
            }
            QPushButton:pressed {
                background-color: #E5E5E5;
            }
            QPushButton:disabled {
                background-color: #F5F5F5;
                color: #AAAAAA;
                border: 1px solid #DDDDDD;
            }
            QStatusBar {
                color: #555555;
                background-color: #F5F5F5;
                border-top: 1px solid #DDDDDD;
                font-size: 12px;
            }
            QLabel {
                color: #333333;
                font-size: 13px;
            }
            QProgressBar {
                text-align: center;
            }
        """)
        
        # Create the threads first
        self.recorder_thread = QThread(self)
        self.player_thread = QThread(self)
        
        # Create workers and move them to their threads
        self.recorder = ActionRecorder()
        self.recorder.moveToThread(self.recorder_thread)
        self.recorder_thread.start()
        
        self.player = ActionPlayer()
        self.player.moveToThread(self.player_thread)
        self.player_thread.start()
        
        # Initialize state
        self.actions = []
        self.is_recording = False
        self.is_playing = False
        
        # Set up UI
        self.init_ui()
        
        # Connect signals
        self.connect_signals()
    
    def init_ui(self):
        # Create central widget with main layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Status layout
        status_layout = QHBoxLayout()
        
        # Status text
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        # Add stretch to push count to right
        status_layout.addStretch()
        
        # Action count
        self.count_label = QLabel("0 actions")
        status_layout.addWidget(self.count_label)
        
        main_layout.addLayout(status_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #EEEEEE;
                border: 1px solid #DDDDDD;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4A90E2;
                border-radius: 2px;
            }
        """)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Create buttons with standard icons
        self.record_button = QPushButton("Record")
        record_icon = QIcon.fromTheme("media-record", QIcon(self.style().standardPixmap(QStyle.SP_DialogApplyButton)))
        self.record_button.setIcon(record_icon)
        self.record_button.clicked.connect(self.toggle_recording)
        button_layout.addWidget(self.record_button)
        
        self.play_button = QPushButton("Play")
        play_icon = QIcon(self.style().standardPixmap(QStyle.SP_MediaPlay))
        self.play_button.setIcon(play_icon)
        self.play_button.clicked.connect(self.toggle_playing)
        self.play_button.setEnabled(False)
        button_layout.addWidget(self.play_button)
        
        self.clear_button = QPushButton("Clear")
        clear_icon = QIcon(self.style().standardPixmap(QStyle.SP_DialogResetButton))
        self.clear_button.setIcon(clear_icon)
        self.clear_button.clicked.connect(self.clear_actions)
        button_layout.addWidget(self.clear_button)
        
        self.save_button = QPushButton("Save")
        save_icon = QIcon(self.style().standardPixmap(QStyle.SP_DialogSaveButton))
        self.save_button.setIcon(save_icon)
        self.save_button.clicked.connect(self.save_actions)
        button_layout.addWidget(self.save_button)
        
        self.load_button = QPushButton("Load")
        load_icon = QIcon(self.style().standardPixmap(QStyle.SP_DialogOpenButton))
        self.load_button.setIcon(load_icon)
        self.load_button.clicked.connect(self.load_actions)
        button_layout.addWidget(self.load_button)
        
        main_layout.addLayout(button_layout)
        
        # Set the central widget
        self.setCentralWidget(central_widget)
        
        # Create status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
        
        # Set application icon
        self.setWindowIcon(QIcon(self.style().standardPixmap(QStyle.SP_DesktopIcon)))
    
    def connect_signals(self):
        # Connect recorder signals
        self.recorder.action_recorded.connect(self.on_action_recorded)
        self.recorder.finished.connect(self.on_recording_finished)
        
        # Connect player signals
        self.player.progress.connect(self.update_play_progress)
        self.player.finished.connect(self.on_playing_finished)
    
    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        self.is_recording = True
        self.record_button.setText("Stop")
        stop_icon = QIcon(self.style().standardPixmap(QStyle.SP_MediaStop))
        self.record_button.setIcon(stop_icon)
        self.record_button.setStyleSheet("QPushButton { background-color: #FFECEC; border: 1px solid #FFBEBE; }")
        self.play_button.setEnabled(False)
        self.status_label.setText("Recording...")
        self.status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
        self.statusBar.showMessage("Recording user actions...")
        
        # Clear previous actions
        self.actions = []
        self.count_label.setText("0 actions")
        
        # Start recording (without moving thread)
        QTimer.singleShot(0, self.recorder.start_recording)
    
    def stop_recording(self):
        if self.is_recording:
            self.is_recording = False
            # Stop recording (without moving thread)
            QTimer.singleShot(0, self.recorder.stop_recording)
    
    def on_recording_finished(self):
        record_icon = QIcon.fromTheme("media-record", QIcon(self.style().standardPixmap(QStyle.SP_DialogApplyButton)))
        self.record_button.setText("Record")
        self.record_button.setIcon(record_icon)
        self.record_button.setStyleSheet("")
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("")
        
        self.actions = self.recorder.actions
        self.count_label.setText(f"{len(self.actions)} action{'s' if len(self.actions) != 1 else ''}")
        
        if self.actions:
            self.play_button.setEnabled(True)
            self.statusBar.showMessage(f"Recorded {len(self.actions)} actions")
        else:
            self.statusBar.showMessage("No actions recorded")
    
    def on_action_recorded(self, action):
        self.actions.append(action)
        self.count_label.setText(f"{len(self.actions)} action{'s' if len(self.actions) != 1 else ''}")
    
    def toggle_playing(self):
        if not self.is_playing:
            self.start_playing()
        else:
            self.stop_playing()
    
    def start_playing(self):
        if not self.actions:
            self.statusBar.showMessage("No actions to play")
            return
        
        self.is_playing = True
        self.play_button.setText("Stop")
        stop_icon = QIcon(self.style().standardPixmap(QStyle.SP_MediaStop))
        self.play_button.setIcon(stop_icon)
        self.play_button.setStyleSheet("QPushButton { background-color: #ECF5FF; border: 1px solid #BEDDFF; }")
        self.record_button.setEnabled(False)
        self.status_label.setText("Playing...")
        self.status_label.setStyleSheet("color: #1976D2; font-weight: bold;")
        self.progress_bar.show()
        self.statusBar.showMessage("Playing recorded actions...")
        
        # Set the actions and play (without moving thread)
        self.player.set_actions(self.actions)
        QTimer.singleShot(0, self.player.play_actions)
    
    def stop_playing(self):
        if self.is_playing:
            # Stop playing (without moving thread)
            QTimer.singleShot(0, self.player.stop_playing)
    
    def on_playing_finished(self):
        play_icon = QIcon(self.style().standardPixmap(QStyle.SP_MediaPlay))
        self.is_playing = False
        self.play_button.setText("Play")
        self.play_button.setIcon(play_icon)
        self.play_button.setStyleSheet("")
        self.record_button.setEnabled(True)
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("")
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.statusBar.showMessage("Playback finished")
    
    def update_play_progress(self, current, total):
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat(f"{progress}% ({current}/{total})")
        self.statusBar.showMessage(f"Playing... {current}/{total} actions")
    
    def clear_actions(self):
        self.actions = []
        self.count_label.setText("0 actions")
        self.play_button.setEnabled(False)
        self.status_label.setText("Actions cleared")
        self.statusBar.showMessage("All actions cleared")
    
    def save_actions(self):
        if not self.actions:
            self.statusBar.showMessage("No actions to save")
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Macro", "", "JSON Files (*.json)"
        )
        
        if filename:
            with open(filename, 'w') as f:
                json.dump(self.actions, f)
            self.status_label.setText(f"Saved {len(self.actions)} actions")
            self.statusBar.showMessage(f"Saved {len(self.actions)} actions to {filename}")
    
    def load_actions(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Macro", "", "JSON Files (*.json)"
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    self.actions = json.load(f)
                    
                self.count_label.setText(f"{len(self.actions)} action{'s' if len(self.actions) != 1 else ''}")
                
                if self.actions:
                    self.play_button.setEnabled(True)
                
                self.status_label.setText(f"Loaded {len(self.actions)} actions")
                self.statusBar.showMessage(f"Loaded {len(self.actions)} actions from {filename}")
            except Exception as e:
                self.statusBar.showMessage(f"Error loading file: {str(e)}")
    
    def closeEvent(self, event):
        # Make sure to stop recording/playing before closing
        if self.is_recording:
            self.stop_recording()
        
        if self.is_playing:
            self.stop_playing()
        
        # Clean up threads
        self.recorder_thread.quit()
        self.recorder_thread.wait()
        self.player_thread.quit()
        self.player_thread.wait()
        
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MacroRecorderApp()
    window.show()
    sys.exit(app.exec_())