#pragma once
#include <cstddef>

namespace spa
{
    // Execute only the immediate seat task. Do not use SetPedInCarDirect: its
    // driver branch installs DriveWander, taking control away from the player.
    // Keep the temporary task alive through processing, then drop its reference
    // before restoring GTA's ordinary player tasks.
    template<class Task, class Construct, class Process, class Destroy, class Restore>
    bool WarpPlayerSeat(Construct construct, Process process, Destroy destroy, Restore restore)
    {
        alignas(Task) std::byte storage[sizeof(Task)];
        Task* task = reinterpret_cast<Task*>(storage);
        construct(task);
        bool completed;
        {
            struct Cleanup
            {
                Task* task;
                Destroy& destroy;
                ~Cleanup() { destroy(task); }
            } cleanup{task, destroy};
            task->m_bWarpingInToCar = true;
            completed = process(task);
        }
        if (completed) restore();
        return completed;
    }
}
