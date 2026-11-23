from tools import extract_contact_from_image
# Замените путь на реальное фото визитки
result = extract_contact_from_image.invoke({"image_path": "/home/italy/Work/dron/Agents/test/cards/card08.jpeg"})
print(result)
