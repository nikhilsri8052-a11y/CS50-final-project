/*
 * planner.c — Daily study topic scheduler
 *
 * Usage:  planner <days_left> <hours_per_day> <topic_data>
 *
 * topic_data format:  "id,difficulty|id,difficulty|..."
 *   Topics should be passed in already in any order; this program will
 *   sort them by difficulty descending (hardest first) so the most
 *   demanding material is tackled earliest.
 *
 * Output: Comma-separated "id:hours" pairs for TODAY's topics only.
 *   e.g.  "3:1.50,7:2.00,1:0.50"
 *
 * Algorithm
 * ---------
 * 1. Sort topics hardest-first.
 * 2. Spread them evenly: each topic occupies ceil(total_topics/days_left)
 *    slots, adjusted so no day is overloaded.
 * 3. Today's slice = topics[0 .. topics_per_day-1].
 * 4. Each topic's hours are proportional to its difficulty share within
 *    today's slice, scaled to exactly hours_per_day (capped at 0.5 h min).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_TOPICS 1000

typedef struct {
    int    id;
    int    difficulty;
} Topic;

/* Descending difficulty comparator for qsort */
static int cmp_desc(const void *a, const void *b)
{
    return ((Topic *)b)->difficulty - ((Topic *)a)->difficulty;
}

int main(int argc, char *argv[])
{
    if (argc < 4) {
        fprintf(stderr, "Usage: planner <days_left> <hours_per_day> <topic_data>\n");
        return 1;
    }

    int    days_left     = atoi(argv[1]);
    double hours_per_day = atof(argv[2]);
    char  *input_data    = argv[3];   /* mutated by strtok */

    /* ── Parse topics ───────────────────────────────────────────────── */
    Topic topics[MAX_TOPICS];
    int   topic_count = 0;

    char *token = strtok(input_data, "|");
    while (token != NULL && topic_count < MAX_TOPICS) {
        int id, diff;
        if (sscanf(token, "%d,%d", &id, &diff) == 2) {
            topics[topic_count].id         = id;
            topics[topic_count].difficulty = diff < 1 ? 1 : diff;
            topic_count++;
        }
        token = strtok(NULL, "|");
    }

    if (topic_count == 0) return 0;

    /* ── Sanitise parameters ────────────────────────────────────────── */
    if (days_left     < 1)   days_left     = 1;
    if (hours_per_day < 0.5) hours_per_day = 0.5;

    /* ── Sort hardest-first ─────────────────────────────────────────── */
    qsort(topics, topic_count, sizeof(Topic), cmp_desc);

    /* ── Decide how many topics to assign today ─────────────────────── */
    /*
     * Basic rule: spread topics as evenly as possible.
     * topics_per_day = ceil(remaining_topics / days_left)
     * This ensures we always finish on time even if we do slightly more
     * on some days.
     */
    int topics_per_day = (topic_count + days_left - 1) / days_left;
    if (topics_per_day < 1) topics_per_day = 1;

    /* Clamp so we never exceed what's left */
    if (topics_per_day > topic_count) topics_per_day = topic_count;

    /* ── Compute each topic's difficulty share → proportional hours ─── */
    int today_diff_total = 0;
    for (int i = 0; i < topics_per_day; i++)
        today_diff_total += topics[i].difficulty;

    /* Avoid division by zero */
    if (today_diff_total == 0) today_diff_total = 1;

    /* ── Output "id:hours" pairs ────────────────────────────────────── */
    for (int i = 0; i < topics_per_day; i++) {
        double topic_hours = ((double)topics[i].difficulty / today_diff_total)
                             * hours_per_day;

        /* Enforce a minimum of 0.5 h per topic so nothing shows as 0 */
        if (topic_hours < 0.5) topic_hours = 0.5;

        if (i > 0) printf(",");
        printf("%d:%.2f", topics[i].id, topic_hours);
    }
    printf("\n");

    return 0;
}