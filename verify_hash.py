from argon2 import PasswordHasher

ph = PasswordHasher()
hash_val = "$argon2id$v=19$m=65536,t=3,p=4$Zb2l836daerXuBldZXMeiw$SZhLMlxhGonA4r3wMI/4HGX+tfH+zFlBnUPUGWTf9hQ"
print("Attempting to verify...")
try:
    ph.verify(hash_val, "123")
    print("Match 123!")
except Exception as e:
    print("123 failed:", type(e).__name__)

try:
    ph.verify(hash_val, "1234")
    print("Match 1234!")
except Exception as e:
    print("1234 failed:", type(e).__name__)
