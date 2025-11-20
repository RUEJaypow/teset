import tkinter as tk
from tkinter import messagebox
import subprocess
import json
import re
import unicodedata
import httpx
from openai import OpenAI

# ───────────────────────────────
# 設定・定数
# ───────────────────────────────
# AI設定
API_BASE_URL = "http://192.168.19.1:11434/v1"
API_KEY = "fake-key"
MODEL_NAME = "gemma3:12b-it-q4_K_M"

# GUI設定（プログラム2のデザインを採用）
COLOR_BG = "#e8f5e9"       # 背景色（薄い緑）
COLOR_TITLE = "#1b5e20"    # タイトル文字色（濃い緑）
COLOR_BTN_MAIN = "#66bb6a" # メインボタン背景
COLOR_BTN_TEXT = "white"   # メインボタン文字
COLOR_TEXT_MAIN = "#2e7d32"

# 外部連携設定（プログラム1の機能）
EXTERNAL_PROGRAM = "pushup_counter.py"


# ───────────────────────────────
# ① ロジッククラス（問題生成・正誤判定）
# ───────────────────────────────
class QuizLogic:
    """
    AIとの通信やクイズの正誤判定などのロジックを担当するクラス
    GUIのコードとは分離しています。
    """
    def __init__(self):
        self.client = OpenAI(
            base_url=API_BASE_URL,
            api_key=API_KEY,
            http_client=httpx.Client(verify=False, timeout=60.0),
        )

    def generate_quiz(self, difficulty, genre):
        """
        指定された難易度とジャンルに基づいてAIで問題を生成する
        プロンプトはプログラム2のものをそのまま使用
        """
        if difficulty == "初級":
            prompt = f"""
        あなたはクイズ作成AIです。
        テーマは「{genre}」です。
        初級レベルの三択問題を1問だけ生成してください。
        JSONのみで出力:

        {{
          "question": "問題文",
          "choices": ["Aの内容", "Bの内容", "Cの内容"],
          "answer": "A" または "B" または "C"
        }}
        """

        elif difficulty == "中級":
            prompt = f"""
        あなたはクイズ作成AIです。
        テーマは「{genre}」です。
        中級レベルの単語入力問題を1問生成してください。
        JSONのみで出力:

        {{
          "question": "問題文",
          "answer": "答えのキーワード"
        }}
        """
        else:
            return None

        # --- AI 実行 ---
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
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
            return user_answer.strip().upper() == quiz["answer"].upper()

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
    """
    ユーザーインターフェースを担当するクラス
    プログラム2のデザイン・レイアウトを採用
    """
    def __init__(self, root):
        self.root = root
        self.logic = QuizLogic() # ロジッククラスのインスタンス化
        
        # 基本ウィンドウ設定
        root.title("IT・プログラミング クイズゲーム")
        root.geometry("600x600")
        root.configure(bg=COLOR_BG)

        # 状態管理変数
        self.difficulty_var = tk.StringVar(value="初級")
        self.genre_var = tk.StringVar(value="IT")
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
        # 既存のフレームがあれば削除（リセット用）
        for widget in self.root.winfo_children():
            widget.destroy()

        # タイトル
        tk.Label(
            self.root, text="プログラミング クイズ",
            font=("Yu Gothic", 24, "bold"),
            bg=COLOR_BG, fg=COLOR_TITLE
        ).pack(pady=20)

        # 難易度設定
        tk.Label(self.root, text="難易度（初級 / 中級）", bg=COLOR_BG).pack()
        tk.Entry(self.root, textvariable=self.difficulty_var).pack(ipady=4)

        # ジャンル設定
        tk.Label(self.root, text="ジャンル（IT / プログラミング）", bg=COLOR_BG).pack(pady=(10, 0))
        tk.Entry(self.root, textvariable=self.genre_var).pack(ipady=4)

        # スタートボタン
        tk.Button(
            self.root, text="クイズ開始",
            font=("Yu Gothic", 12, "bold"),
            bg=COLOR_BTN_MAIN, fg=COLOR_BTN_TEXT,
            command=self.start_quiz,
            width=20, height=2
        ).pack(pady=15)

    def start_quiz(self):
        """クイズの初期化と開始"""
        self.difficulty = self.difficulty_var.get()
        self.genre = self.genre_var.get()
        
        # カウンターリセット
        self.correct_count = 0
        self.wrong_count = 0
        self.question_index = 0
        self.asked_questions = set()
        
        # 画面遷移（設定パーツを消去）
        for widget in self.root.winfo_children():
            widget.destroy()
            
        self.show_next_question()

    def show_next_question(self):
        """次の問題を表示"""
        # 前の問題フレームを削除
        if self.quiz_frame:
            self.quiz_frame.destroy()

        # 10問終了したら結果画面へ
        if self.question_index >= 10:
            self.show_final_result()
            return

        # 問題生成（ロジッククラスに委譲）
        quiz = None
        for _ in range(10): # 重複回避のため最大10回試行
            quiz = self.logic.generate_quiz(self.difficulty, self.genre)
            if quiz and quiz["question"] not in self.asked_questions:
                break
        
        if not quiz:
            messagebox.showerror("エラー", "問題生成に失敗しました")
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
        A, B, C = quiz["choices"]
        for label, text in zip(["A", "B", "C"], [A, B, C]):
            tk.Button(
                self.quiz_frame,
                text=f"{label}: {text}",
                bg="#81c784", fg="black",
                font=("Yu Gothic", 14),
                width=30, height=2,
                command=lambda x=label: self.check_answer_gui(x)
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
        """
        全問終了後の結果画面
        ここでプログラム1の機能（外部プログラム起動）を統合
        """
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

        # ★統合ポイント: プログラム1の終了・連携機能
        tk.Button(
            result_frame, text="終了して運動する",
            bg="#ef5350", fg="white", # 赤系で強調
            font=("Yu Gothic", 12, "bold"),
            width=20,
            command=self.run_external_and_exit
        ).pack(pady=20)

    def run_external_and_exit(self):
        """外部プログラム(pushup_counter.py)を実行して終了"""
        self.root.destroy()
        try:
            subprocess.run(["python", EXTERNAL_PROGRAM])
        except FileNotFoundError:
            # 万が一ファイルがない場合のエラーハンドリング（念のためコンソール出力）
            print(f"エラー: {EXTERNAL_PROGRAM} が見つかりませんでした。")


# ───────────────────────────────
# ③ メイン実行処理
# ───────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = QuizApp(root)
    root.mainloop()