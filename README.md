# 10桁の円周率を求めるPythonスクリプト

このディレクトリには、10桁の円周率を計算するためのPythonスクリプトが含まれています。

## 計算方法

以下のPythonスクリプトを使用して10桁の円周率を計算します。

```python
def calculate_pi(num_terms):
    pi = 0.0
    for k in range(num_terms):
        pi += ((-1) ** k) / (2 * k + 1)
    return pi * 4

if __name__ == '__main__':
    num_terms = 1000000  # 計算に使用する項数
    print(f'10桁の円周率: {calculate_pi(num_terms):.10f}')
```

このスクリプトでは、マクローリン級数を使用して円周率を計算しています。
