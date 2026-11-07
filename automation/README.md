# Playbook-файлы развёртывания

Запускайте команды из этого каталога на управляющем Linux/WSL-узле.

```bash
python3 -m venv .venv
source .venv/bin/activate
export ANSIBLE_CONFIG="$PWD/ansible.cfg"
pip install -r requirements.txt
ansible-galaxy role install -r requirements.yml -p roles
cp inventory/group_vars/cpnginx.yml.example inventory/group_vars/cpnginx.yml
```

Скорректируйте `inventory/hosts.yml` для своих тестовых узлов. Используйте
SSH-ключ, укажите `CPNGINX_SSH_USER`; для sudo при необходимости передайте `-K`.
Задайте `VAULT_ADDR`, `VAULT_ROLE_ID` и `VAULT_SECRET_ID` из закрытого источника.
Предоставьте локальный дистрибутив КриптоПро абсолютным путём:

```bash
ansible-playbook playbooks/site.yml -K -e cpnginx_install_deb_packet=/absolute/path/linux-amd64_deb.tgz
```

Отдельные playbook-файлы: `cpnginx_install.yaml`, `cpnginx_configure.yaml`.
`scripts/run-playbook.sh` поддерживает команды `install`, `configure`, `site`.
По умолчанию используется исполняемый файл `ansible-playbook` из PATH.
Для Vault CLI при необходимости используется wrapper из `../lab/vault/bin`.

`inventory` внутри этого каталога содержит узлы Ansible, а `../inventory`
содержит YAML-описания интеграций. Они имеют разные назначения.
Роли загружаются из отдельных GitHub-репозиториев; готовые копии `roles/`
не включаются в Git. Рабочий файл с переменными также игнорируется.
Полный запуск требует собственного Vault, тестовых ключей, лицензии при
необходимости и доступных узлов. Его выполнение не является частью публикации.
