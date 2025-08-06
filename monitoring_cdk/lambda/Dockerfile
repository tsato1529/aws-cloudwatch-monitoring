FROM public.ecr.aws/lambda/python:3.11

# ライブラリインストール
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Lambda関数本体をコピー
COPY notify.py .

# ハンドラー関数の場所を指定
CMD ["notify.handler"]

