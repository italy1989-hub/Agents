import hashlib
import sys
import store

sha = hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest()
store.delete(sha)
print("Запись о визитке удалена, её можно обработать заново.")
