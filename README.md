# にょん姉貴が登場☆ver1.1

Python製のデスクトップマスコットです。PySide6で動作し、キャラクターのアニメーションや音声再生、各種表示設定に対応しています。

## 起動

Python 3.14で動作確認済みです。依存ライブラリを用意したうえで、プロジェクト直下から起動します。

```bash
python main.py
```

## 素材の差し替え

画像素材はプロジェクト直下の `assets/` に配置します。状態ごとの画像は `assets/<状態名>/`、音声は `assets/voices/<イベント名>/` に置きます。素材は差し替えて利用できます。

## EXE化

PySide6を使用しています。`main.py` が起動ファイルで、EXE化する場合のエントリポイントです。
"python -m PyInstaller --noconsole --noconfirm main.py"でコンパイル
アイコンを設定したい場合
"python -m PyInstaller --noconsole --noconfirm --icon=アイコンのファイル名.ico main.py"でコンパイル

## 使用したNYN姉貴素材

sm30598781.mp4
sm31945874.mp4
sm30761410.mp4
sm32184120.mp4
sm33898287.mp4
https://www.axfc.net/u/3844454.zip








