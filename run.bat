@echo off
chcp 65001 >nul
REM 一键跑：自检 → 样例报告 → 批量跑批
REM 依赖：python 在 PATH 中（本项目仅需标准库）

echo [1/3] 自检...
python -m tests.selftest
if errorlevel 1 goto fail

echo.
echo [2/3] 样例报告...
python -m tickercheck.cli -i samples/holdings.csv -o out/report.html --as-of %date:~0,4%-%date:~5,2%-%date:~8,2%
if errorlevel 1 goto fail

echo.
echo [3/3] 批量跑批...
python -m scripts.batch --inbox submissions --outdir out/batch --week W1
goto end

:fail
echo.
echo [失败] 上面的报错先修掉再跑。
pause
exit /b 1

:end
echo.
echo [完成] 报告在 out\ 目录，双击 HTML 即可查看。
pause
