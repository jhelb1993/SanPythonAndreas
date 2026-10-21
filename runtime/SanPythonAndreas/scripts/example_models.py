"""U loads Infernus model 411 asynchronously; I cancels. No vehicle is spawned.

Import example_models in main.py. A ready model is held for three game seconds.
"""
import sanandreas as sa

_task = None


def _load():
    try:
        sa.show_text("Modell 411 wird asynchron geladen...")
        with (yield from sa.load_model(411, timeout=10)) as model:
            print("Modell bereit:", model.model_id, model.ready)
            sa.show_text("Modell 411 bereit. Freigabe in 3 Spielsekunden.")
            yield sa.wait(3)
        print("Modell 411 freigegeben")
        sa.show_text("Modell 411 freigegeben.")
    except (TimeoutError, RuntimeError) as error:
        print("Modellladen fehlgeschlagen:", error)
        if sa.player() is not None:
            sa.show_text("Modellladen fehlgeschlagen. Details im Python-Log.")
    finally:
        print("Modell-Task aufgeraeumt")


@sa.on_key_down("U")
def load_infernus_model():
    global _task
    if _task is not None and not _task.done:
        _task.cancel()
    _task = sa.start_task(_load())


@sa.on_key_down("I")
def cancel_model_load():
    if _task is not None and not _task.done:
        _task.cancel()
    sa.show_text("Modell-Task abgebrochen.")
