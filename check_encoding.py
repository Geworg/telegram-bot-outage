import os

for root, dirs, files in os.walk("."):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, encoding="utf-8") as f:
                    f.read()
            except UnicodeDecodeError as e:
                print(f"❌ Проблема в файле: {path}\n{e}\n")
