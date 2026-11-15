# にょん姉貴が登場☆ver1.1

Python製。PySide6で動作し、キャラクターのアニメーションや音声再生、各種表示設定に対応しています。

## 起動

Python 3.14で動作確認済みです。依存ライブラリを用意したうえで、プロジェクト直下から起動します。

```bash
python main.py
```

## 素材の入れ方

画像素材はプロジェクト直下の `assets/` に配置します。状態ごとの画像は `assets/<状態名>/`、音声は `assets/voices/<イベント名>/` に置きます。素材は差し替えて利用できます。素材がない場合は、簡易的なキャラクターが生成されます。素材の形式はPNG連番。nyn姉貴の素材は容量が大きくアップロードできなかったので以下のリンクから配布。assetsごと置き換えればnyn姉貴がデスクトップ上に現れる。
https://41.gigafile.nu/1120-k42c1743e0c7f957ddebde5e9013fa555

## EXE化

PySide6を使用しています。`main.py` が起動ファイルで、EXE化する場合のエントリポイントです。
"python -m PyInstaller --noconsole --noconfirm main.py"でコンパイルしてください
アイコンを設定したい場合
"python -m PyInstaller --noconsole --noconfirm --icon=アイコンのファイル名.ico main.py"でコンパイルしてください
コンパイルすると、main.pyと同じ場所にdistフォルダが作成され、その中にmain.exeが作成されます。
exe化した場合、main.exeと同じ場所にassetsフォルダを再配置してください。



