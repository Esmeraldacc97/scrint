from django.contrib.auth import get_user_model

# Obtener el modelo de usuario
User = get_user_model()

# Lista de usuarios a crear
usuarios = [
    {'username': 'estudiante1_p1', 'email': 'estudiante1_p1@correo.com', 'password': '12345'},
{'username': 'estudiante2_p1', 'email': 'estudiante2_p1@correo.com', 'password': '12345'},
{'username': 'estudiante3_p1', 'email': 'estudiante3_p1@correo.com', 'password': '12345'},
{'username': 'estudiante4_p1', 'email': 'estudiante4_p1@correo.com', 'password': '12345'},
{'username': 'estudiante5_p1', 'email': 'estudiante5_p1@correo.com', 'password': '12345'},

]

for datos in usuarios:
    user, creado = User.objects.get_or_create(
        username=datos['username'],
        defaults={
            'email': datos['email'],
            'is_active': True
        }
    )
    if creado:
        user.set_password(datos['password'])
        user.save()
        print(f"✅ Usuario creado: {datos['username']}")
    else:
        print(f"ℹ️ Usuario ya existe: {datos['username']}")
