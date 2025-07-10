import polib

po = polib.pofile("locale/en/LC_MESSAGES/django.po")
po.save_as_mofile("locale/en/LC_MESSAGES/django.mo")
print("✅ Перевод скомпилирован.")
