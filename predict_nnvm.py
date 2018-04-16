#! python3

import sys

# 入力値チェック
if len(sys.argv) < 2:
    print('Usage: python3 {} filepath'.format(sys.argv[0]))
    quit()


import nnvm
import tvm
from tvm.contrib import graph_runtime
import numpy as np
from pathlib import Path
import keras
from keras.preprocessing import image
from keras.models import model_from_json
# from keras.applications.inception_v3 import preprocess_input
# from keras.applications.vgg19 import preprocess_input
from keras.applications.resnet50 import preprocess_input


# データパス
LABEL_FILE = 'label.txt'
MODEL_NAME = 'model.json'
WEIGHT_DIR = 'weight'
TARGET_LIST = ['opencl', 'llvm', 'cuda', 'metal', 'opengl', 'vulkan']
TARGET = TARGET_LIST[0]


# ラベルのロード
label = open(LABEL_FILE, 'r').read().split('\n')

# モデルのロード
model = model_from_json(open(MODEL_NAME, 'r').read())
model.load_weights(sorted(Path(WEIGHT_DIR).glob('*'))[-1])
# from keras.models import load_model
# model = load_model("model.h5")
# model.compile(loss='categorical_crossentropy',
#             optimizer='adam',
#             metrics=['accuracy'])

# KerasのモデルをNNVMで読み込む
sym, params = nnvm.frontend.from_keras(model)

# CoreML を経由して読み込む (Only Python2)
# import coremltools
# model.save('model.h5')
# coreml_model = coremltools.converters.keras.convert('model.h5',
#                                         input_names='features',
#                                         image_input_names='labels',
#                                         class_labels='label.txt')
# sym, params = nnvm.frontend.from_coreml(coreml_model)

# モデルのコンパイル
shape_dict = {'data': (1, 3, 224, 224)}
with nnvm.compiler.build_config(opt_level=3):
    graph, lib, params = nnvm.compiler.build(sym, TARGET, shape_dict, params=params)

ctx = tvm.context(TARGET, 0)
m = graph_runtime.create(graph, lib, ctx)


# 画像から入力データを作成
for img_path in sys.argv[1:]:
    # 入力データのセット
    img = image.load_img(img_path, target_size=(224, 224))
    x = image.img_to_array(img)
    x = np.expand_dims(x, axis=0)
    x = preprocess_input(x).transpose([0, 3, 1, 2])

    # 推論実行
    m.set_input('data', tvm.nd.array(x.astype(keras.backend.floatx())))
    m.set_input(**params)
    m.run()

    # 計算結果を取得し、推論結果を確認
    out_shape = (len(label),)
    tvm_out = m.get_output(0, tvm.nd.empty(out_shape, keras.backend.floatx())).asnumpy()
    pred = dict(zip(label, tvm_out))
    ranking = sorted(pred.items(), key=lambda x: -x[1])

    # 推論結果を出力
    print('\nFile: {}'.format(img_path))
    print('Predicted: {}'.format(label[np.argmax(tvm_out)]))
    for i, v in enumerate(ranking):
        print(i, v)
        if i > 5:
            break
