#部署用脚本

wget https://m645b3e1bb36e-mrap.mrap.accesspoint.tos-global.volces.com/linux/amd64/tosutil
chmod +x tosutil
./tosutil config -i "your_access_key" -k "your_secret_key" -e tos-cn-beijing.volces.com -re cn-beijing
pip install volcengine-python-sdk