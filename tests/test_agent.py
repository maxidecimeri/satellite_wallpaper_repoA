from satellite_wallpaper.agent import run

def test_run(capsys):
    run()
    out = capsys.readouterr().out
    assert "running" in out
