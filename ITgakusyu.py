# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox
import subprocess
import json
import re
import unicodedata
import httpx
from openai import OpenAI
import csv
import random
import os
import pandas as pd  # pandasを追加

# ───────────────────────────────
# 設定・定数
# ───────────────────────────────
# AI設定
API_BASE_URL = "http://192.168.19.1:11434/v1"
API_KEY = "fake-key"
MODEL_NAME = "gemma3:12b-it-q4_K_M"

# GUI設定
COLOR_BG = "#e8f5e9"        # 背景色（薄い緑）
COLOR_TITLE = "#1b5e20"     # タイトル文字色（濃い緑）
COLOR_BTN_MAIN = "#66bb6a"  # メインボタン背景
COLOR_BTN_TEXT = "white"    # メインボタン文字
COLOR_TEXT_MAIN = "#2e7d32"

# 外部連携設定
EXTERNAL_PROGRAM = "pushup_counter.py"


# ───────────────────────────────
# ① ロジッククラス（問題生成・正誤判定）
# ───────────────────────────────
class QuizLogic:
    """
    AIとの通信やクイズの正誤判定、CSV読み込みを担当するクラス
    """
    def __init__(self):
        self.client = OpenAI(
            base_url=API_BASE_URL,
            api_key=API_KEY,
            http_client=httpx.Client(verify=False, timeout=60.0),
        )

    def load_random_csv_data(self, filepath, num_samples=5):
        """
        CSVファイルを読み込み、ランダムに数行を抽出してテキストとして返す
        pandasを使用してShift-JISで読み込む
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"ファイルが見つかりません: {filepath}")

        try:
            # pandasを使用してShift_JISで読み込み (header=Noneですべてデータとして扱う)
            df = pd.read_csv(filepath, encoding='shift_jis', header=None)
            
            if df.empty:
                return "データがありません。"

            # データ量が多すぎる場合のためにランダムサンプリング
            if len(df) > num_samples:
                sampled_df = df.sample(n=num_samples)
            else:
                sampled_df = df
            
            # データフレームをCSV形式の文字列に変換して返す（インデックスとヘッダーは含めない）
            return sampled_df.to_csv(index=False, header=False)

        except Exception as e:
            raise RuntimeError(f"CSV読み込みエラー: {e}")

    def generate_quiz(self, difficulty, csv_filename):
        """
        指定されたCSVファイルの内容に基づいてAIで問題を生成する
        """
        # CSVデータを取得
        try:
            csv_content = self.load_random_csv_data(csv_filename)
        except Exception as e:
            print(e)
            return None

        # プロンプト作成
        base_instruction = f"""
        あなたはクイズ作成AIです。
        以下の【CSVデータ】の内容**のみ**に基づいて、クイズを1問作成してください。
        問題の形式としては、文章列の文章からキーワード1**または**キーワード2を○○に変換して生成してください。
        外部知識は使用しないでください。
        
        【CSVデータ】
        {csv_content}
        """

        if difficulty == "初級":
            prompt = base_instruction + """
            初級レベルの三択問題を生成してください。
            JSONのみで出力:
            {
              "question": "問題文",
              "choices": ["選択肢1", "選択肢2", "選択肢3"],
              "answer": "正解の選択肢の文字列（choicesに含まれるものと完全に一致させること）"
            }
            """
        elif difficulty == "中級":
            prompt = base_instruction + """
            中級レベルの単語入力問題（記述式）を生成してください。
            答えはCSVデータに含まれる単語にしてください。
            JSONのみで出力:
            {
              "question": "問題文",
              "answer": "答えのキーワード"
            }
            """
        else:
            return None

        # --- AI 実行 ---
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7, # 少し創造性を下げる（データに忠実にするため）
            )
            text = response.choices[0].message.content

            # --- JSON抽出 ---
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return None
            return json.loads(match.group())
        except Exception as e:
            print(f"Error generating quiz: {e}")
            return None

    def check_answer(self, difficulty, quiz, user_answer):
        """ユーザーの回答を判定する"""
        if difficulty == "初級":
            # 記号ではなく文字列で比較
            return user_answer == quiz["answer"]

        elif difficulty == "中級":
            def normalize(t):
                t = unicodedata.normalize("NFKC", t.lower())
                return "".join(
                    c for c in t if c.isalnum() or "\u3040" <= c <= "\u9faf"
                )
            return normalize(user_answer) in normalize(quiz["answer"])

        return False


# ───────────────────────────────
# ② GUIクラス（画面描画）
# ───────────────────────────────
class QuizApp:
    def __init__(self, root):
        self.root = root
        self.logic = QuizLogic() 
        
        # 基本ウィンドウ設定
        root.title("CSVデータ クイズ生成機")
        root.geometry("600x600")
        root.configure(bg=COLOR_BG)

        # 状態管理変数
        self.difficulty_var = tk.StringVar(value="初級")
        self.csv_file_var = tk.StringVar(value="data.csv") # デフォルトCSVファイル名
        self.current_quiz = None
        self.correct_count = 0
        self.wrong_count = 0
        self.question_index = 0
        self.asked_questions = set()
        self.quiz_frame = None

        # スタート画面の描画
        self.setup_start_screen()

    def setup_start_screen(self):
        """スタート画面（設定画面）の構築"""
        for widget in self.root.winfo_children():
            widget.destroy()

        # タイトル
        tk.Label(
            self.root, text="IT学習 クイズ",
            font=("Yu Gothic", 24, "bold"),
            bg=COLOR_BG, fg=COLOR_TITLE
        ).pack(pady=20)

        # 難易度設定
        tk.Label(self.root, text="難易度を選択してください", bg=COLOR_BG, font=("Yu Gothic", 12)).pack(pady=(20, 5))

        # ラジオボタン用のフレーム
        radio_frame = tk.Frame(self.root, bg=COLOR_BG)
        radio_frame.pack(pady=5)

        tk.Radiobutton(
            radio_frame, text="初級 (3択)", variable=self.difficulty_var, value="初級",
            bg=COLOR_BG, activebackground=COLOR_BG, font=("Yu Gothic", 11)
        ).pack(side=tk.LEFT, padx=10)

        tk.Radiobutton(
            radio_frame, text="中級 (記述)", variable=self.difficulty_var, value="中級",
            bg=COLOR_BG, activebackground=COLOR_BG, font=("Yu Gothic", 11)
        ).pack(side=tk.LEFT, padx=10)

        # CSVファイル設定は非表示（デフォルトの data.csv を使用）

        # スタートボタン
        tk.Button(
            self.root, text="クイズ開始",
            font=("Yu Gothic", 12, "bold"),
            bg=COLOR_BTN_MAIN, fg=COLOR_BTN_TEXT,
            command=self.start_quiz,
            width=20, height=2
        ).pack(pady=40)

    def start_quiz(self):
        """クイズの初期化と開始"""
        self.difficulty = self.difficulty_var.get()
        self.csv_filename = self.csv_file_var.get()
        
        # ファイル存在チェック
        if not os.path.exists(self.csv_filename):
            messagebox.showerror("エラー", f"ファイル '{self.csv_filename}' が見つかりません。")
            return

        # カウンターリセット
        self.correct_count = 0
        self.wrong_count = 0
        self.question_index = 0
        self.asked_questions = set()
        
        # 画面遷移
        for widget in self.root.winfo_children():
            widget.destroy()
            
        self.show_next_question()

    def show_next_question(self):
        """次の問題を表示"""
        if self.quiz_frame:
            self.quiz_frame.destroy()

        # 10問終了したら結果画面へ
        if self.question_index >= 10:
            self.show_final_result()
            return

        # ローディング表示（AI待ち）
        loading_label = tk.Label(self.root, text="問題を生成中...", bg=COLOR_BG, font=("Yu Gothic", 12))
        loading_label.pack(pady=50)
        self.root.update() # 画面更新

        # 問題生成
        quiz = None
        for _ in range(5): # リトライ回数
            quiz = self.logic.generate_quiz(self.difficulty, self.csv_filename)
            if quiz and quiz["question"] not in self.asked_questions:
                break
        
        loading_label.destroy()

        if not quiz:
            messagebox.showerror("エラー", "問題生成に失敗しました。\nCSVファイルの内容を確認してください。")
            self.show_final_result()
            return

        self.current_quiz = quiz
        self.asked_questions.add(quiz["question"])
        self.question_index += 1

        # --- UI 構築 ---
        self.quiz_frame = tk.Frame(self.root, bg=COLOR_BG)
        self.quiz_frame.pack(pady=20, fill="both", expand=True)

        # 問題番号
        tk.Label(
            self.quiz_frame, text=f"第 {self.question_index} 問",
            bg=COLOR_BG, fg=COLOR_TEXT_MAIN, font=("Yu Gothic", 16, "bold")
        ).pack(pady=5)

        # 問題文
        tk.Label(
            self.quiz_frame, text=quiz["question"],
            wraplength=500, justify="center",
            bg=COLOR_BG, font=("Yu Gothic", 14)
        ).pack(pady=10)

        # 選択肢または入力欄の表示
        if self.difficulty == "初級":
            self.create_choice_buttons(quiz)
        else:
            self.create_input_field()

    def create_choice_buttons(self, quiz):
        """初級用：三択ボタンの生成"""
        choices = quiz["choices"]
        # A, B, C のラベルは表示用として生成
        labels = ["A", "B", "C"]
        
        for label, text in zip(labels, choices):
            tk.Button(
                self.quiz_frame,
                text=f"{label}: {text}",
                bg="#81c784", fg="black",
                font=("Yu Gothic", 14),
                width=30, height=2,
                # ラベルではなくテキストそのものを渡す
                command=lambda x=text: self.check_answer_gui(x)
            ).pack(pady=5)

    def create_input_field(self):
        """中級用：入力フィールドの生成"""
        self.entry = tk.Entry(self.quiz_frame, font=("Yu Gothic", 14), width=30)
        self.entry.pack(pady=10, ipady=5)

        tk.Button(
            self.quiz_frame, text="回答する",
            bg="#fbc02d", fg="black",
            font=("Yu Gothic", 14, "bold"),
            width=20, height=2,
            command=lambda: self.check_answer_gui(self.entry.get())
        ).pack(pady=10)

    def check_answer_gui(self, user_answer):
        """回答チェックと中間結果表示"""
        is_correct = self.logic.check_answer(self.difficulty, self.current_quiz, user_answer)

        if is_correct:
            messagebox.showinfo("結果", "正解！")
            self.correct_count += 1
        else:
            messagebox.showinfo("結果", f"不正解… 正解は「{self.current_quiz['answer']}」")
            self.wrong_count += 1

        self.show_next_question()

    def show_final_result(self):
        """全問終了後の結果画面"""
        if self.quiz_frame:
            self.quiz_frame.destroy()

        result_frame = tk.Frame(self.root, bg=COLOR_BG)
        result_frame.pack(pady=50, fill="both", expand=True)

        # 結果テキスト
        tk.Label(
            result_frame, text="クイズ終了！",
            bg=COLOR_BG, fg=COLOR_TITLE, font=("Yu Gothic", 24, "bold")
        ).pack(pady=20)

        result_text = f"正解：{self.correct_count}問\n不正解：{self.wrong_count}問"
        tk.Label(
            result_frame, text=result_text,
            bg=COLOR_BG, font=("Yu Gothic", 18)
        ).pack(pady=20)

        # 再挑戦ボタン
        tk.Button(
            result_frame, text="タイトルに戻る",
            bg=COLOR_BTN_MAIN, fg=COLOR_BTN_TEXT,
            font=("Yu Gothic", 12),
            width=20,
            command=self.setup_start_screen
        ).pack(pady=10)

        # 終了して運動するボタン
        tk.Button(
            result_frame, text="終了して運動する",
            bg="#ef5350", fg="white",
            font=("Yu Gothic", 12, "bold"),
            width=20,
            command=self.run_external_and_exit
        ).pack(pady=20)

    def run_external_and_exit(self):
        """外部プログラムを実行して終了"""
        self.root.destroy()
        try:
            subprocess.run(["python", EXTERNAL_PROGRAM])
        except FileNotFoundError:
            print(f"エラー: {EXTERNAL_PROGRAM} が見つかりませんでした。")


# ───────────────────────────────
# ③ メイン実行処理
# ───────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = QuizApp(root)
    root.mainloop()