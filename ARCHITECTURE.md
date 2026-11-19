# アーキテクチャ(デスクトップマスコット)

起動: `python main.py`(または `python -m mascot`)。素材は `main.py` と同じ場所の `assets/` に置く(従来どおり)。
exe化する場合のエントリは `main.py`。

## 構成と責務

```
main.py                      起動スクリプト(mascot.app.run を呼ぶだけ)
mascot/
  config.py                  設定・パス・定数・設定ファイルの読み書き      ← 最下層。何にも依存しない
  diagnostics.py             ログ設定
  system/memory.py           OS依存の処理(メモリ使用量・未使用領域の返却)  ← OSごとの分岐はここへ
  imaging/                   【画像管理】
    lru.py                     バイト数上限つきLRU
    backend.py                 Qt の画像処理(読込・縮小・反転・ロスレス圧縮)
    store.py                   2層キャッシュ・世代管理・読み込みスレッド・先読み
  animation/                 【アニメーション管理】
    animation.py               連番1セット。「いま表示するコマ」を返す
    sprites.py                 assets/<状態>/ を束ねる。サイズ変更・起動時の優先読み込み
    placeholder.py             素材が無いときの簡易キャラ
  audio/voice.py             【音声再生】語録の再生
  ui/                        【画面】
    pet.py                     キャラクター本体(ウィンドウ・物理・入力・描画)
    settings.py                設定ダイアログ
  startup/                   【起動時読み込み】
    loading_window.py          「読み込み中」画面
    bootstrap.py               起動の進行役(組み立て役)
  app.py                     QApplication を作って Bootstrap を動かす
tools/check_architecture.py  依存関係の自動検査
tests/                       検証スクリプト(PySide6なしで中核ロジックを検証)
```

## 依存の規則(上位 → 下位の一方向のみ)

```
app → startup → ui ─────────────┐
           │                     ├→ diagnostics, system → config
           ├→ animation → imaging ┤
           └→ audio ──────────────┘
```

* **ui は animation / audio / imaging を import しない。** Pet は Sprites と VoicePlayer を引数で受け取る
  (依存性注入)。組み立ては startup/bootstrap.py だけが行う。
* 相対 import は使わない(`from mascot.xxx import ...` に統一)。
* `__init__.py` には処理を書かない(循環インポートの温床になるため)。
* 関数の中での遅延 import も同じ規則で検査される。
* 規則の本体は `tools/check_architecture.py` の `ALLOWED`。**新しいパッケージや依存を足すときは、
  先に ALLOWED を更新してから実装する。** 変更のたびに `python tools/check_architecture.py` を実行する。

## 起動の流れ

`app.run()` → ログ設定 → `QApplication` → `Bootstrap.start()`
1. 読み込み画面を表示(LoadingWindow)
2. `Sprites` を作る(素材確認。画像本体は読まない)→ 必須コマを読み込みスレッドへ依頼
3. 並行して `VoicePlayer` を初期化
4. 必須コマが揃う(またはタイムアウト)→ `Pet(cfg, sprites, voice)` を表示 → 読み込み画面を閉じる

## 機能追加の置き場所(案)

| 追加したい機能 | 置き場所 | 依存してよい先(ALLOWED に追加) |
|---|---|---|
| 会話機能 | `mascot/conversation/` を新設 | config, diagnostics, audio |
| ウィンドウ上の歩行 | OS別の取得処理を `mascot/system/windows_info.py` に置き、**取得口(関数/クラス)を Pet に注入** | config |
| 複数OS対応 | OS依存の処理は `mascot/system/` に集める | config |

* 会話機能は Pet を直接 import せず、Bootstrap が `Pet` に渡す(または Qt の Signal でやり取りする)。
* ウィンドウ上の歩行は、他ウィンドウの位置の取得方法がOSで大きく違う
  (Windows/macOS は可能、Linux の Wayland は原則取得不可)。取得できない環境では
  「画面の下端だけを歩く」現在の動作に戻せるよう、注入する取得口は「失敗したら空リストを返す」形にする。

## 未実施の分割(次の段階の候補)

* `ui/pet.py`(約470行)は、ウィンドウ・物理(歩行/落下/壁)・入力(クリック/ドラッグ)・描画・メニューが
  1クラスに同居している。今回は「機能維持」を優先して手を入れていない。
  分けるなら、物理(`ui/physics.py`)→ 描画(`ui/painter.py`)の順が安全。
* 分割の前に、Pet の物理計算を Qt から切り離した単体テストを用意すること。
